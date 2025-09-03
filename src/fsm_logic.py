"""
FSM Logic for Vulcan Sentinel

Implements the finite state machine for automatic detection of heating stages
and generation of automatic reports.
"""

import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class ZoneSnapshot:
    """Snapshot of a zone's current state"""
    T: float                    # Current temperature
    SP_active: float            # Active setpoint
    SP_cmd: float              # Commanded setpoint
    SP_idle: float             # Idle setpoint
    valid: bool                # Sensor validity
    timestamp: datetime        # When snapshot was taken


@dataclass
class FSMEvent:
    """Event emitted by the FSM"""
    kind: str                  # Event type
    run_id: str                # Associated run ID
    stage: str                 # Stage name
    timestamp: datetime        # Event timestamp
    data: Dict[str, Any]      # Additional event data


class FSMStateMachine:
    """Finite State Machine for heating process detection"""
    
    def __init__(self, line_id: str, config: Dict[str, Any]):
        self.line_id = line_id
        self.config = config
        
        # Current state
        self.state = "IDLE"
        self.run_id = None
        self.current_stage = None
        self.stage_start_time = None
        self.sp_ref = None
        
        # Stage tracking
        self.stages = {}
        self.stage_stats = {}
        
        # Timing and validation
        self.last_transition_time = datetime.now()
        self.quiet_start_time = None
        self.quiet_timer = None
        
        # Statistics accumulation (Welford's method)
        self._init_stats()
        
        logger.info(f"FSM initialized for {line_id} with config version {config.get('version', 1)}")
        
    def _init_stats(self):
        """Initialize statistics tracking for all stages"""
        for stage in ['preheat', 'main_heat', 'rib_heat']:
            self.stage_stats[stage] = {
                'count': 0,
                'mean': 0.0,
                'M2': 0.0,  # For variance calculation
                'min': float('inf'),
                'max': float('-inf'),
                'start_time': None,
                'sp_start': None,
                'sp_end': None
            }
            
    def on_sample(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process a new sample and return any events"""
        events = []
        
        try:
            # Update statistics for current stage
            if self.current_stage and self.current_stage in zones:
                self._update_stage_stats(self.current_stage, zones[self.current_stage], timestamp)
            
            # Process state transitions
            if self.state == "IDLE":
                events.extend(self._process_idle_state(timestamp, zones))
            elif self.state == "PREHEAT_RAMP":
                events.extend(self._process_preheat_ramp_state(timestamp, zones))
            elif self.state == "PREHEAT_STABLE":
                events.extend(self._process_preheat_stable_state(timestamp, zones))
            elif self.state == "PREHEAT_END":
                events.extend(self._process_preheat_end_state(timestamp, zones))
            elif self.state == "MAIN_RAMP":
                events.extend(self._process_main_ramp_state(timestamp, zones))
            elif self.state == "MAIN_STABLE":
                events.extend(self._process_main_stable_state(timestamp, zones))
            elif self.state == "MAIN_END":
                events.extend(self._process_main_end_state(timestamp, zones))
            elif self.state == "RIB_RAMP":
                events.extend(self._process_rib_ramp_state(timestamp, zones))
            elif self.state == "RIB_STABLE":
                events.extend(self._process_rib_stable_state(timestamp, zones))
            elif self.state == "RIB_END":
                events.extend(self._process_rib_end_state(timestamp, zones))
                
            # Check for quiet timeout
            events.extend(self._check_quiet_timeout(timestamp, zones))
            
            # Check for stage timeouts
            events.extend(self._check_stage_timeouts(timestamp))
            
        except Exception as e:
            logger.error(f"Error in FSM state processing: {e}")
            events.append(FSMEvent(
                kind="FSM_ERROR",
                run_id=self.run_id or "unknown",
                stage=self.current_stage or "unknown",
                timestamp=timestamp,
                data={"error": str(e)}
            ))
            
        return events
        
    def _process_idle_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process IDLE state - look for start conditions"""
        events = []
        
        # Check if preheat is starting
        if self._should_start_preheat(zones):
            events.append(self._start_stage("preheat", timestamp, zones))
            
        return events
        
    def _process_preheat_ramp_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process PREHEAT_RAMP state"""
        events = []
        
        preheat = zones.get('preheat')
        if not preheat or not preheat.valid:
            events.append(self._end_stage_fault("preheat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if reached stable temperature
        if self._is_in_band(preheat.T, preheat.SP_active):
            events.append(self._transition_to_stable("preheat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("preheat", timestamp):
            events.append(self._end_stage_timeout("preheat", timestamp))
            
        return events
        
    def _process_preheat_stable_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process PREHEAT_STABLE state"""
        events = []
        
        preheat = zones.get('preheat')
        if not preheat or not preheat.valid:
            events.append(self._end_stage_fault("preheat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if still in band
        if not self._is_in_band(preheat.T, preheat.SP_active):
            events.append(self._end_stage_normal("preheat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("preheat", timestamp):
            events.append(self._end_stage_timeout("preheat", timestamp))
            
        return events
        
    def _process_preheat_end_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process PREHEAT_END state - look for next stage"""
        events = []
        
        # Check if main heat is starting
        if self._should_start_main_heat(zones):
            events.append(self._start_stage("main_heat", timestamp, zones))
        else:
            # Start quiet timer
            if not self.quiet_start_time:
                self.quiet_start_time = timestamp
                self.quiet_timer = self.config.get('quiet_window_s', 720)
                
        return events
        
    def _process_main_ramp_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process MAIN_RAMP state"""
        events = []
        
        main_heat = zones.get('main_heat')
        if not main_heat or not main_heat.valid:
            events.append(self._end_stage_fault("main_heat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if reached stable temperature
        if self._is_in_band(main_heat.T, main_heat.SP_active):
            events.append(self._transition_to_stable("main_heat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("main_heat", timestamp):
            events.append(self._end_stage_timeout("main_heat", timestamp))
            
        return events
        
    def _process_main_stable_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process MAIN_STABLE state"""
        events = []
        
        main_heat = zones.get('main_heat')
        if not main_heat or not main_heat.valid:
            events.append(self._end_stage_fault("main_heat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if still in band
        if not self._is_in_band(main_heat.T, main_heat.SP_active):
            events.append(self._end_stage_normal("main_heat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("main_heat", timestamp):
            events.append(self._end_stage_timeout("main_heat", timestamp))
            
        return events
        
    def _process_main_end_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process MAIN_END state - look for next stage"""
        events = []
        
        # Check if rib heat is starting
        if self._should_start_rib_heat(zones):
            events.append(self._start_stage("rib_heat", timestamp, zones))
        else:
            # Start quiet timer
            if not self.quiet_start_time:
                self.quiet_start_time = timestamp
                self.quiet_timer = self.config.get('quiet_window_s', 720)
                
        return events
        
    def _process_rib_ramp_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process RIB_RAMP state"""
        events = []
        
        rib_heat = zones.get('rib_heat')
        if not rib_heat or not rib_heat.valid:
            events.append(self._end_stage_fault("rib_heat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if reached stable temperature
        if self._is_in_band(rib_heat.T, rib_heat.SP_active):
            events.append(self._transition_to_stable("rib_heat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("rib_heat", timestamp):
            events.append(self._end_stage_timeout("rib_heat", timestamp))
            
        return events
        
    def _process_rib_stable_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process RIB_STABLE state"""
        events = []
        
        rib_heat = zones.get('rib_heat')
        if not rib_heat or not rib_heat.valid:
            events.append(self._end_stage_fault("rib_heat", timestamp, "Invalid sensor data"))
            return events
            
        # Check if still in band
        if not self._is_in_band(rib_heat.T, rib_heat.SP_active):
            events.append(self._end_stage_normal("rib_heat", timestamp))
            
        # Check for timeout
        if self._is_stage_timeout("rib_heat", timestamp):
            events.append(self._end_stage_timeout("rib_heat", timestamp))
            
        return events
        
    def _process_rib_end_state(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process RIB_END state - generate full report"""
        events = []
        
        # Generate full report event
        events.append(FSMEvent(
            kind="FULL_REPORT",
            run_id=self.run_id,
            stage="rib_heat",
            timestamp=timestamp,
            data={
                "end_reason": "normal",
                "preheat_ok": "preheat" in self.stages,
                "main_ok": "main_heat" in self.stages,
                "rib_ok": "rib_heat" in self.stages
            }
        ))
        
        # Reset to IDLE
        self._reset_to_idle()
        
        return events
        
    def _should_start_preheat(self, zones: Dict[str, ZoneSnapshot]) -> bool:
        """Check if preheat should start"""
        preheat = zones.get('preheat')
        if not preheat or not preheat.valid:
            return False
            
        # Check for setpoint jump or temperature ramp
        if self._is_setpoint_jump(preheat.SP_active):
            return True
            
        if self._is_ramping_up(preheat.T, preheat.SP_active):
            return True
            
        return False
        
    def _should_start_main_heat(self, zones: Dict[str, ZoneSnapshot]) -> bool:
        """Check if main heat should start"""
        main_heat = zones.get('main_heat')
        if not main_heat or not main_heat.valid:
            return False
            
        # Check for setpoint jump or temperature ramp
        if self._is_setpoint_jump(main_heat.SP_active):
            return True
            
        if self._is_ramping_up(main_heat.T, main_heat.SP_active):
            return True
            
        return False
        
    def _should_start_rib_heat(self, zones: Dict[str, ZoneSnapshot]) -> bool:
        """Check if rib heat should start"""
        rib_heat = zones.get('rib_heat')
        if not rib_heat or not rib_heat.valid:
            return False
            
        # Check for setpoint jump or temperature ramp
        if self._is_setpoint_jump(rib_heat.SP_active):
            return True
            
        if self._is_ramping_up(rib_heat.T, rib_heat.SP_active):
            return True
            
        return False
        
    def _is_in_band(self, temperature: float, setpoint: float) -> bool:
        """Check if temperature is within tolerance band of setpoint"""
        tol = self.config.get('Tol_F', 8)
        return abs(temperature - setpoint) <= tol
        
    def _is_setpoint_jump(self, setpoint: float) -> bool:
        """Check if setpoint has jumped significantly"""
        if self.sp_ref is None:
            return False
            
        s_min = self.config.get('S_min_F', 20)
        return abs(setpoint - self.sp_ref) >= s_min
        
    def _is_ramping_up(self, temperature: float, setpoint: float) -> bool:
        """Check if temperature is ramping up significantly"""
        # This is a simplified check - in practice, you'd track temperature history
        # and calculate actual slope
        delta_ramp = self.config.get('DeltaRamp_F', 20)
        return temperature >= setpoint + delta_ramp
        
    def _start_stage(self, stage_name: str, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> FSMEvent:
        """Start a new stage"""
        import uuid
        
        if not self.run_id:
            self.run_id = f"RUN_{timestamp.strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
            
        self.current_stage = stage_name
        self.stage_start_time = timestamp
        self.sp_ref = zones[stage_name].SP_active
        
        # Initialize stage statistics
        self.stage_stats[stage_name]['start_time'] = timestamp
        self.stage_stats[stage_name]['sp_start'] = self.sp_ref
        
        # Set state based on stage
        if stage_name == 'preheat':
            self.state = 'PREHEAT_RAMP'
        elif stage_name == 'main_heat':
            self.state = 'MAIN_RAMP'
        elif stage_name == 'rib_heat':
            self.state = 'RIB_RAMP'
            
        logger.info(f"Started stage {stage_name} at {timestamp}")
        
        return FSMEvent(
            kind="STAGE_START",
            run_id=self.run_id,
            stage=stage_name,
            timestamp=timestamp,
            data={"sp_ref": self.sp_ref}
        )
        
    def _transition_to_stable(self, stage_name: str, timestamp: datetime) -> FSMEvent:
        """Transition stage from ramp to stable"""
        if stage_name == 'preheat':
            self.state = 'PREHEAT_STABLE'
        elif stage_name == 'main_heat':
            self.state = 'MAIN_STABLE'
        elif stage_name == 'rib_heat':
            self.state = 'RIB_STABLE'
            
        logger.info(f"Stage {stage_name} reached stable at {timestamp}")
        
        return FSMEvent(
            kind="STAGE_STABLE",
            run_id=self.run_id,
            stage=stage_name,
            timestamp=timestamp,
            data={}
        )
        
    def _end_stage_normal(self, stage_name: str, timestamp: datetime) -> FSMEvent:
        """End stage normally"""
        self._finalize_stage(stage_name, timestamp, 'normal')
        
        # Set state based on stage
        if stage_name == 'preheat':
            self.state = 'PREHEAT_END'
        elif stage_name == 'main_heat':
            self.state = 'MAIN_END'
        elif stage_name == 'rib_heat':
            self.state = 'RIB_END'
            
        logger.info(f"Stage {stage_name} ended normally at {timestamp}")
        
        return FSMEvent(
            kind="STAGE_END",
            run_id=self.run_id,
            stage=stage_name,
            timestamp=timestamp,
            data={"status": "normal"}
        )
        
    def _end_stage_fault(self, stage_name: str, timestamp: datetime, reason: str) -> FSMEvent:
        """End stage due to fault"""
        self._finalize_stage(stage_name, timestamp, 'fault')
        
        # Set state based on stage
        if stage_name == 'preheat':
            self.state = 'PREHEAT_END'
        elif stage_name == 'main_heat':
            self.state = 'MAIN_END'
        elif stage_name == 'rib_heat':
            self.state = 'RIB_END'
            
        logger.warning(f"Stage {stage_name} ended with fault at {timestamp}: {reason}")
        
        return FSMEvent(
            kind="STAGE_END",
            run_id=self.run_id,
            stage=stage_name,
            timestamp=timestamp,
            data={"status": "fault", "reason": reason}
        )
        
    def _end_stage_timeout(self, stage_name: str, timestamp: datetime) -> FSMEvent:
        """End stage due to timeout"""
        self._finalize_stage(stage_name, timestamp, 'timeout')
        
        # Set state based on stage
        if stage_name == 'preheat':
            self.state = 'PREHEAT_END'
        elif stage_name == 'main_heat':
            self.state = 'MAIN_END'
        elif stage_name == 'rib_heat':
            self.state = 'RIB_END'
            
        logger.warning(f"Stage {stage_name} ended with timeout at {timestamp}")
        
        return FSMEvent(
            kind="STAGE_END",
            run_id=self.run_id,
            stage=stage_name,
            timestamp=timestamp,
            data={"status": "timeout"}
        )
        
    def _finalize_stage(self, stage_name: str, timestamp: datetime, status: str):
        """Finalize stage statistics and tracking"""
        if stage_name in self.stage_stats:
            stats = self.stage_stats[stage_name]
            stats['sp_end'] = self.sp_ref
            stats['end_time'] = timestamp
            
            # Store stage in stages dict
            self.stages[stage_name] = {
                'start_time': stats['start_time'],
                'end_time': timestamp,
                'sp_start': stats['sp_start'],
                'sp_end': stats['sp_end'],
                't_min': stats['min'],
                't_max': stats['max'],
                't_mean': stats['mean'],
                't_std': math.sqrt(stats['M2'] / stats['count']) if stats['count'] > 0 else 0,
                'status': status
            }
            
        self.current_stage = None
        self.stage_start_time = None
        
    def _update_stage_stats(self, stage_name: str, zone: ZoneSnapshot, timestamp: datetime):
        """Update stage statistics using Welford's method"""
        if stage_name not in self.stage_stats:
            return
            
        stats = self.stage_stats[stage_name]
        
        if stats['start_time'] is None:
            stats['start_time'] = timestamp
            stats['sp_start'] = zone.SP_active
            
        # Update min/max
        stats['min'] = min(stats['min'], zone.T)
        stats['max'] = max(stats['max'], zone.T)
        
        # Update mean and variance using Welford's method
        stats['count'] += 1
        delta = zone.T - stats['mean']
        stats['mean'] += delta / stats['count']
        delta2 = zone.T - stats['mean']
        stats['M2'] += delta * delta2
        
    def _is_stage_timeout(self, stage_name: str, timestamp: datetime) -> bool:
        """Check if stage has timed out"""
        if not self.stage_start_time:
            return False
            
        if self.state.endswith('_RAMP'):
            max_time = self.config.get('Max_ramp_s', 900)
        else:
            max_time = self.config.get('Max_stage_s', 7200)
            
        elapsed = (timestamp - self.stage_start_time).total_seconds()
        return elapsed > max_time
        
    def _check_quiet_timeout(self, timestamp: datetime, zones: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Check for quiet timeout and generate partial report"""
        events = []
        
        if not self.quiet_start_time:
            return events
            
        elapsed = (timestamp - self.quiet_start_time).total_seconds()
        if elapsed >= self.quiet_timer:
            # Generate partial report
            events.append(FSMEvent(
                kind="PARTIAL_REPORT",
                run_id=self.run_id,
                stage="quiet_timeout",
                timestamp=timestamp,
                data={
                    "end_reason": "quiet_timeout",
                    "preheat_ok": "preheat" in self.stages,
                    "main_ok": "main_heat" in self.stages,
                    "rib_ok": "rib_heat" in self.stages
                }
            ))
            
            # Reset to IDLE
            self._reset_to_idle()
            
        return events
        
    def _check_stage_timeouts(self, timestamp: datetime) -> List[FSMEvent]:
        """Check for stage timeouts"""
        events = []
        
        if self.current_stage and self._is_stage_timeout(self.current_stage, timestamp):
            events.append(self._end_stage_timeout(self.current_stage, timestamp))
            
        return events
        
    def _reset_to_idle(self):
        """Reset FSM to IDLE state"""
        self.state = "IDLE"
        self.run_id = None
        self.current_stage = None
        self.stage_start_time = None
        self.sp_ref = None
        self.quiet_start_time = None
        self.quiet_timer = None
        self._init_stats()
        self.stages.clear()
        
    def reset_to_idle(self):
        """Public method to reset FSM to IDLE state"""
        self._reset_to_idle()
        logger.info("FSM reset to IDLE state")
        
    def get_current_state(self) -> Dict[str, Any]:
        """Get current FSM state for debugging/monitoring"""
        return {
            'state': self.state,
            'run_id': self.run_id,
            'current_stage': self.current_stage,
            'stage_start_time': self.stage_start_time,
            'sp_ref': self.sp_ref,
            'stages': self.stages,
            'quiet_start_time': self.quiet_start_time,
            'quiet_timer': self.quiet_timer
        }
