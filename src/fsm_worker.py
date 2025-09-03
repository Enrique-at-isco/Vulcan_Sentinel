"""
FSM Worker Service for Vulcan Sentinel

Runs alongside the existing Modbus poller to provide real-time FSM processing
for automatic report generation.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from queue import Queue, Full
import threading

from .fsm_logic import FSMStateMachine, ZoneSnapshot, FSMEvent
from .database import DatabaseManager
from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


class FSMWorker:
    """FSM Worker service that runs alongside existing Modbus poller"""
    
    def __init__(self, db_manager: DatabaseManager, config_manager: ConfigManager, line_id: str = "Line-07"):
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.line_id = line_id
        
        # FSM state machine
        self.fsm = None
        self.fsm_config = None
        
        # Threading and queues
        self.sample_queue = Queue(maxsize=300)  # Bounded queue for samples
        self.running = False
        self.worker_thread = None
        self.sampler_thread = None
        
        # Device configuration
        self.devices_config = None
        self.enabled_zones = []
        
        # Statistics
        self.samples_processed = 0
        self.events_generated = 0
        self.last_sample_time = None
        
        logger.info(f"FSM Worker initialized for {line_id}")
        
    def start(self):
        """Start the FSM worker service"""
        if self.running:
            logger.warning("FSM Worker already running")
            return
            
        try:
            # Load configuration
            self._load_configuration()
            
            # Initialize FSM
            self._initialize_fsm()
            
            # Start worker threads
            self.running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.sampler_thread = threading.Thread(target=self._sampler_loop, daemon=True)
            
            self.worker_thread.start()
            self.sampler_thread.start()
            
            logger.info("FSM Worker started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start FSM Worker: {e}")
            self.running = False
            raise
            
    def stop(self):
        """Stop the FSM worker service"""
        if not self.running:
            return
            
        logger.info("Stopping FSM Worker...")
        self.running = False
        
        # Wait for threads to finish
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5.0)
        if self.sampler_thread and self.sampler_thread.is_alive():
            self.sampler_thread.join(timeout=5.0)
            
        logger.info("FSM Worker stopped")
        
    def _load_configuration(self):
        """Load FSM configuration from database"""
        try:
            # Get FSM config from database
            self.fsm_config = self.db_manager.get_fsm_config(self.line_id)
            if not self.fsm_config:
                logger.warning(f"No FSM config found for {self.line_id}, using defaults")
                self.fsm_config = self._get_default_config()
                
            # Load devices configuration
            self.devices_config = self.config_manager.load_devices_config()
            
            # Determine enabled zones
            self.enabled_zones = []
            for device_id, device_config in self.devices_config['devices'].items():
                sensor_name = device_config['name']
                if sensor_name in ['preheat', 'main_heat', 'rib_heat']:
                    self.enabled_zones.append(sensor_name)
                    
            logger.info(f"Loaded FSM config for zones: {self.enabled_zones}")
            
        except Exception as e:
            logger.error(f"Failed to load FSM configuration: {e}")
            raise
            
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default FSM configuration"""
        return {
            'sampling_period_s': 2.0,
            'Tol_F': 8,
            'DeltaRamp_F': 20,
            'dT_min_F_per_min': 10,
            'T_stable_s': 90,
            'DeltaOff_F': 20,
            'T_off_sustain_s': 45,
            'S_min_F': 20,
            'T_sp_sustain_s': 20,
            'Max_ramp_s': 900,
            'Max_stage_s': 7200,
            'quiet_window_s': 720,
            'dT_quiet_F_per_min': 2,
            'allow_main_without_preheat': True,
            'continue_after_fault_if_next_stage_ramps': True
        }
        
    def _initialize_fsm(self):
        """Initialize the FSM state machine"""
        try:
            # Get current runtime state from database
            runtime_state = self.db_manager.get_fsm_runtime_state(self.line_id)
            
            # Initialize FSM
            self.fsm = FSMStateMachine(self.line_id, self.fsm_config)
            
            # Restore state if available
            if runtime_state:
                self.fsm.state = runtime_state['state']
                self.fsm.run_id = runtime_state['run_id']
                self.fsm.current_stage = runtime_state['stage']
                if runtime_state['stage_enter_ts']:
                    self.fsm.stage_start_time = datetime.fromisoformat(runtime_state['stage_enter_ts'])
                self.fsm.sp_ref = runtime_state['sp_ref']
                logger.info(f"Restored FSM state: {self.fsm.state}")
            else:
                logger.info("Starting FSM in IDLE state")
                
        except Exception as e:
            logger.error(f"Failed to initialize FSM: {e}")
            raise
            
    def _sampler_loop(self):
        """Sample loop that reads Modbus registers and queues samples"""
        logger.info("FSM Sampler loop started")
        
        while self.running:
            try:
                # Read current values from all enabled zones
                zones_snapshot = self._read_zones_snapshot()
                
                if zones_snapshot:
                    # Queue the snapshot for processing
                    try:
                        self.sample_queue.put_nowait(zones_snapshot)
                        self.last_sample_time = datetime.now()
                    except Full:
                        # Queue is full, remove oldest sample
                        try:
                            _ = self.sample_queue.get_nowait()
                            self.sample_queue.put_nowait(zones_snapshot)
                            logger.warning("FSM sample queue was full, dropped oldest sample")
                        except Full:
                            logger.error("FSM sample queue is still full after dropping oldest")
                            
                # Sleep for sampling period
                time.sleep(self.fsm_config.get('sampling_period_s', 2.0))
                
            except Exception as e:
                logger.error(f"Error in FSM sampler loop: {e}")
                time.sleep(1.0)  # Brief pause on error
                
        logger.info("FSM Sampler loop stopped")
        
    def _worker_loop(self):
        """Worker loop that processes queued samples and runs FSM logic"""
        logger.info("FSM Worker loop started")
        
        while self.running:
            try:
                # Get sample from queue (blocking with timeout)
                try:
                    zones_snapshot = self.sample_queue.get(timeout=1.0)
                except:
                    continue  # Timeout, check if still running
                    
                # Process sample through FSM
                events = self._process_sample(zones_snapshot)
                
                # Handle events
                for event in events:
                    self._handle_fsm_event(event)
                    
                # Update runtime state in database
                self._update_runtime_state()
                
                # Update statistics
                self.samples_processed += 1
                self.events_generated += len(events)
                
            except Exception as e:
                logger.error(f"Error in FSM worker loop: {e}")
                # Reset FSM to IDLE on error
                if self.fsm:
                    self.fsm.reset_to_idle()
                    
        logger.info("FSM Worker loop stopped")
        
    def _read_zones_snapshot(self) -> Optional[Dict[str, ZoneSnapshot]]:
        """Read current snapshot from all enabled zones"""
        try:
            zones = {}
            
            for zone_name in self.enabled_zones:
                # Find device config for this zone
                device_config = None
                for device_id, config in self.devices_config['devices'].items():
                    if config['name'] == zone_name:
                        device_config = config
                        break
                        
                if not device_config:
                    logger.warning(f"No device config found for zone {zone_name}")
                    continue
                    
                # Read zone snapshot
                zone_snapshot = self._read_zone_snapshot(zone_name, device_config)
                if zone_snapshot:
                    zones[zone_name] = zone_snapshot
                    
            return zones if zones else None
            
        except Exception as e:
            logger.error(f"Failed to read zones snapshot: {e}")
            return None
            
    def _read_zone_snapshot(self, zone_name: str, device_config: Dict[str, Any]) -> Optional[ZoneSnapshot]:
        """Read snapshot for a single zone"""
        try:
            # For now, we'll use the existing database readings
            # In a full implementation, this would read directly from Modbus
            
            # Get latest reading from database
            latest_readings = self.db_manager.get_latest_readings()
            
            # Extract temperature and setpoint for this zone
            temperature = None
            setpoint = None
            
            for reading in latest_readings:
                if reading['sensor_name'] == zone_name:
                    temperature = reading.get('temperature')
                    setpoint = reading.get('setpoint')
                    break
                    
            if temperature is None or setpoint is None:
                logger.warning(f"Missing data for zone {zone_name}")
                return None
                
            # Create zone snapshot
            # Note: In full implementation, we'd read SP_cmd, SP_idle, and AI_error from Modbus
            return ZoneSnapshot(
                T=float(temperature),
                SP_active=float(setpoint),
                SP_cmd=float(setpoint),  # Same as active for now
                SP_idle=float(setpoint),  # Same as active for now
                valid=True,  # Assume valid for now
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to read zone snapshot for {zone_name}: {e}")
            return None
            
    def _process_sample(self, zones_snapshot: Dict[str, ZoneSnapshot]) -> List[FSMEvent]:
        """Process a sample through the FSM"""
        try:
            if not self.fsm:
                return []
                
            # Get current timestamp
            timestamp = datetime.now()
            
            # Process through FSM
            events = self.fsm.on_sample(timestamp, zones_snapshot)
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to process FSM sample: {e}")
            return []
            
    def _handle_fsm_event(self, event: FSMEvent):
        """Handle an FSM event"""
        try:
            logger.info(f"FSM Event: {event.kind} for {event.stage} at {event.timestamp}")
            
            if event.kind == "STAGE_START":
                self._handle_stage_start(event)
            elif event.kind == "STAGE_STABLE":
                self._handle_stage_stable(event)
            elif event.kind == "STAGE_END":
                self._handle_stage_end(event)
            elif event.kind == "FULL_REPORT":
                self._handle_full_report(event)
            elif event.kind == "PARTIAL_REPORT":
                self._handle_partial_report(event)
            elif event.kind == "FSM_ERROR":
                self._handle_fsm_error(event)
                
        except Exception as e:
            logger.error(f"Failed to handle FSM event {event.kind}: {e}")
            
    def _handle_stage_start(self, event: FSMEvent):
        """Handle stage start event"""
        try:
            # Create FSM run if this is the first stage
            if not self.db_manager.get_fsm_runs(self.line_id, limit=1):
                self.db_manager.create_fsm_run(event.run_id, self.line_id, event.timestamp)
                logger.info(f"Created FSM run {event.run_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle stage start: {e}")
            
    def _handle_stage_stable(self, event: FSMEvent):
        """Handle stage stable event"""
        # No database action needed for stable transition
        pass
        
    def _handle_stage_end(self, event: FSMEvent):
        """Handle stage end event"""
        try:
            # Get stage statistics from FSM
            if event.stage in self.fsm.stages:
                stage_data = self.fsm.stages[event.stage]
                
                # Add stage to database
                self.db_manager.add_fsm_stage(
                    run_id=event.run_id,
                    stage=event.stage,
                    start_ts=stage_data['start_time'],
                    end_ts=stage_data['end_time'],
                    sp_start=stage_data['sp_start'],
                    sp_end=stage_data['sp_end'],
                    t_min=stage_data['t_min'],
                    t_max=stage_data['t_max'],
                    t_mean=stage_data['t_mean'],
                    t_std=stage_data['t_std'],
                    status=event.data.get('status', 'normal')
                )
                
                logger.info(f"Added stage {event.stage} to FSM run {event.run_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle stage end: {e}")
            
    def _handle_full_report(self, event: FSMEvent):
        """Handle full report event"""
        try:
            # End FSM run
            self.db_manager.end_fsm_run(
                run_id=event.run_id,
                ended_at=event.timestamp,
                end_reason=event.data.get('end_reason', 'normal'),
                preheat_ok=event.data.get('preheat_ok', False),
                main_ok=event.data.get('main_ok', False),
                rib_ok=event.data.get('rib_ok', False)
            )
            
            logger.info(f"Completed FSM run {event.run_id} with full report")
            
            # TODO: Trigger automatic report generation
            # This will integrate with the existing report generation system
            
        except Exception as e:
            logger.error(f"Failed to handle full report: {e}")
            
    def _handle_partial_report(self, event: FSMEvent):
        """Handle partial report event"""
        try:
            # End FSM run
            self.db_manager.end_fsm_run(
                run_id=event.run_id,
                ended_at=event.timestamp,
                end_reason=event.data.get('end_reason', 'quiet_timeout'),
                preheat_ok=event.data.get('preheat_ok', False),
                main_ok=event.data.get('main_ok', False),
                rib_ok=event.data.get('rib_ok', False)
            )
            
            logger.info(f"Completed FSM run {event.run_id} with partial report")
            
            # TODO: Trigger automatic report generation
            # This will integrate with the existing report generation system
            
        except Exception as e:
            logger.error(f"Failed to handle partial report: {e}")
            
    def _handle_fsm_error(self, event: FSMEvent):
        """Handle FSM error event"""
        try:
            logger.error(f"FSM Error in run {event.run_id}: {event.data.get('error', 'Unknown error')}")
            
            # Reset FSM to IDLE
            if self.fsm:
                self.fsm.reset_to_idle()
                
            # TODO: Log error to database and potentially notify operators
            
        except Exception as e:
            logger.error(f"Failed to handle FSM error: {e}")
            
    def _update_runtime_state(self):
        """Update runtime state in database"""
        try:
            if not self.fsm:
                return
                
            current_state = self.fsm.get_current_state()
            
            self.db_manager.update_fsm_runtime_state(
                line_id=self.line_id,
                state=current_state['state'],
                stage=current_state['current_stage'] or 'none',
                run_id=current_state['run_id'],
                sp_ref=current_state['sp_ref']
            )
            
        except Exception as e:
            logger.error(f"Failed to update runtime state: {e}")
            
    def get_status(self) -> Dict[str, Any]:
        """Get current status of the FSM worker"""
        return {
            'running': self.running,
            'line_id': self.line_id,
            'samples_processed': self.samples_processed,
            'events_generated': self.events_generated,
            'last_sample_time': self.last_sample_time.isoformat() if self.last_sample_time else None,
            'queue_size': self.sample_queue.qsize(),
            'fsm_state': self.fsm.get_current_state() if self.fsm else None
        }
        
    def get_fsm_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent FSM runs"""
        try:
            return self.db_manager.get_fsm_runs(self.line_id, limit)
        except Exception as e:
            logger.error(f"Failed to get FSM runs: {e}")
            return []
