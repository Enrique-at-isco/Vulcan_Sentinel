#!/usr/bin/env python3
"""
Test script for FSM implementation

This script tests the FSM worker and logic without affecting the main application.
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta

# Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.database import DatabaseManager
from src.config_manager import ConfigManager
from src.fsm_worker import FSMWorker
from src.fsm_logic import FSMStateMachine, ZoneSnapshot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_fsm_logic():
    """Test the FSM logic independently"""
    logger.info("Testing FSM Logic...")
    
    # Create test configuration
    test_config = {
        'sampling_period_s': 1.0,
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
    
    # Create FSM instance
    fsm = FSMStateMachine("Line-07", test_config)
    
    # Test initial state
    assert fsm.state == "IDLE", f"Expected IDLE state, got {fsm.state}"
    logger.info("✓ Initial state is IDLE")
    
    # Test state transitions with mock data
    timestamp = datetime.now()
    
    # Mock zone data - preheat starting
    zones = {
        'preheat': ZoneSnapshot(
            T=75.0,           # Current temperature
            SP_active=300.0,   # Setpoint (high enough to trigger start)
            SP_cmd=300.0,
            SP_idle=75.0,
            valid=True,
            timestamp=timestamp
        ),
        'main_heat': ZoneSnapshot(
            T=75.0,
            SP_active=75.0,
            SP_cmd=75.0,
            SP_idle=75.0,
            valid=True,
            timestamp=timestamp
        )
    }
    
    # Process sample
    events = fsm.on_sample(timestamp, zones)
    
    # Check if preheat started
    assert fsm.state == "PREHEAT_RAMP", f"Expected PREHEAT_RAMP state, got {fsm.state}"
    assert fsm.current_stage == "preheat", f"Expected preheat stage, got {fsm.current_stage}"
    logger.info("✓ Preheat stage started correctly")
    
    # Test reaching stable temperature
    timestamp += timedelta(seconds=1)
    zones['preheat'].T = 295.0  # Within tolerance band
    
    events = fsm.on_sample(timestamp, zones)
    
    # Check if reached stable
    assert fsm.state == "PREHEAT_STABLE", f"Expected PREHEAT_STABLE state, got {fsm.state}"
    logger.info("✓ Preheat reached stable state")
    
    # Test stage completion
    timestamp += timedelta(seconds=1)
    zones['preheat'].T = 270.0  # Below tolerance band
    
    events = fsm.on_sample(timestamp, zones)
    
    # Check if stage ended
    assert fsm.state == "PREHEAT_END", f"Expected PREHEAT_END state, got {fsm.state}"
    logger.info("✓ Preheat stage ended correctly")
    
    # Test main heat starting
    timestamp += timedelta(seconds=1)
    zones['main_heat'].SP_active = 400.0  # High setpoint
    
    events = fsm.on_sample(timestamp, zones)
    
    # Check if main heat started
    assert fsm.state == "MAIN_RAMP", f"Expected MAIN_RAMP state, got {fsm.state}"
    assert fsm.current_stage == "main_heat", f"Expected main_heat stage, got {fsm.current_stage}"
    logger.info("✓ Main heat stage started correctly")
    
    logger.info("✓ FSM Logic tests passed!")


def test_fsm_worker():
    """Test the FSM worker service"""
    logger.info("Testing FSM Worker...")
    
    try:
        # Initialize components
        config_manager = ConfigManager()
        db_manager = DatabaseManager()
        
        # Create FSM worker
        fsm_worker = FSMWorker(db_manager, config_manager)
        
        # Test initialization
        assert fsm_worker is not None, "FSM Worker should be created"
        assert fsm_worker.line_id == "Line-07", f"Expected Line-07, got {fsm_worker.line_id}"
        logger.info("✓ FSM Worker created successfully")
        
        # Test configuration loading
        fsm_worker._load_configuration()
        assert fsm_worker.fsm_config is not None, "FSM config should be loaded"
        logger.info("✓ FSM configuration loaded")
        
        # Test FSM initialization
        fsm_worker._initialize_fsm()
        assert fsm_worker.fsm is not None, "FSM should be initialized"
        logger.info("✓ FSM initialized successfully")
        
        # Test status method
        status = fsm_worker.get_status()
        assert 'running' in status, "Status should contain running field"
        assert 'line_id' in status, "Status should contain line_id field"
        logger.info("✓ Status method works")
        
        logger.info("✓ FSM Worker tests passed!")
        
    except Exception as e:
        logger.error(f"FSM Worker test failed: {e}")
        raise


def test_database_integration():
    """Test FSM database integration"""
    logger.info("Testing FSM Database Integration...")
    
    try:
        # Initialize database
        db_manager = DatabaseManager()
        
        # Test FSM config methods
        config = db_manager.get_fsm_config("Line-07")
        assert config is not None, "Should get default FSM config"
        logger.info("✓ FSM config retrieved from database")
        
        # Test runtime state methods
        runtime_state = db_manager.get_fsm_runtime_state("Line-07")
        assert runtime_state is not None, "Should get runtime state"
        # The state could be any valid FSM state since it persists between runs
        valid_states = ['IDLE', 'PREHEAT_RAMP', 'PREHEAT_STABLE', 'PREHEAT_END', 
                       'MAIN_RAMP', 'MAIN_STABLE', 'MAIN_END', 
                       'RIB_RAMP', 'RIB_STABLE', 'RIB_END']
        assert runtime_state['state'] in valid_states, f"Expected valid FSM state, got {runtime_state['state']}"
        logger.info(f"✓ Runtime state retrieved from database: {runtime_state['state']}")
        
        # Test FSM runs methods
        runs = db_manager.get_fsm_runs("Line-07", limit=10)
        assert isinstance(runs, list), "Should return list of runs"
        logger.info("✓ FSM runs retrieved from database")
        
        logger.info("✓ FSM Database Integration tests passed!")
        
    except Exception as e:
        logger.error(f"FSM Database Integration test failed: {e}")
        raise


def main():
    """Run all FSM tests"""
    logger.info("Starting FSM Tests...")
    
    try:
        # Test FSM logic
        test_fsm_logic()
        
        # Test FSM worker
        test_fsm_worker()
        
        # Test database integration
        test_database_integration()
        
        logger.info("🎉 All FSM tests passed successfully!")
        
    except Exception as e:
        logger.error(f"❌ FSM tests failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
