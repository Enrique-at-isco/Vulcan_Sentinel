# FSM Implementation for Vulcan Sentinel

## Overview

The Finite State Machine (FSM) implementation provides automatic detection of heating stages and automatic report generation for the Vulcan Sentinel system. This system runs alongside the existing Modbus poller and provides real-time process monitoring.

## Architecture

### Components

1. **FSM Logic (`fsm_logic.py`)**
   - Core state machine implementation
   - Handles state transitions and stage detection
   - Processes temperature and setpoint data

2. **FSM Worker (`fsm_worker.py`)**
   - Service that runs alongside existing Modbus poller
   - Samples data at configurable intervals (default: 2 seconds)
   - Manages FSM state and database operations

3. **Database Integration (`database.py`)**
   - FSM-specific tables for state tracking
   - Run history and stage statistics
   - Configuration management

4. **Web Interface (`fsm_dashboard.html`)**
   - Real-time monitoring of FSM status
   - Configuration editing
   - Run history viewing

### Database Schema

#### FSM Tables

- **`fsm_runtime_state`**: Current FSM state for each line
- **`fsm_runs`**: Run history with completion status
- **`fsm_stages`**: Per-stage statistics and timing
- **`fsm_config`**: Versioned configuration parameters

## Configuration

### Default Parameters

```yaml
sampling_period_s: 2.0          # FSM sampling interval
Tol_F: 8                        # ±8°F tolerance band
DeltaRamp_F: 20                 # 20°F rise for ramp detection
dT_min_F_per_min: 10            # 10°F/min minimum slope
T_stable_s: 90                  # 90 seconds to mark stable
DeltaOff_F: 20                  # 20°F below setpoint to exit
T_off_sustain_s: 45             # 45 seconds out of band
S_min_F: 20                     # 20°F minimum setpoint change
T_sp_sustain_s: 20              # 20 seconds setpoint must remain
Max_ramp_s: 900                 # 15 minutes max ramp time
Max_stage_s: 7200               # 2 hours max stage duration
quiet_window_s: 720             # 12 minutes quiet period
dT_quiet_F_per_min: 2           # 2°F/min quiet threshold
allow_main_without_preheat: true
continue_after_fault_if_next_stage_ramps: true
```

### Device Mapping

The system automatically maps to your existing device configuration:

- **Preheat**: Instance 1 (registers 402, 2172, etc.)
- **Main Heat**: Instance 2 (registers 482, 2252, etc.)
- **Rib Heat**: Instance 3 (registers 562, 2332, etc.)

## State Machine

### States

1. **IDLE**: Waiting for process to start
2. **PREHEAT_RAMP**: Preheat temperature ramping up
3. **PREHEAT_STABLE**: Preheat at target temperature
4. **PREHEAT_END**: Preheat stage completed
5. **MAIN_RAMP**: Main heat temperature ramping up
6. **MAIN_STABLE**: Main heat at target temperature
7. **MAIN_END**: Main heat stage completed
8. **RIB_RAMP**: Rib heat temperature ramping up
9. **RIB_STABLE**: Rib heat at target temperature
10. **RIB_END**: Rib heat stage completed

### Transitions

- **Start Detection**: Setpoint jump or temperature ramp
- **Stable Detection**: Temperature within tolerance band for specified time
- **End Detection**: Temperature drops below exit threshold
- **Timeout Protection**: Maximum time limits for each stage
- **Fault Handling**: Invalid sensor data or communication errors

## Usage

### Starting the System

The FSM worker starts automatically with the main application:

```bash
# The FSM worker is integrated into main.py
python src/main.py
```

### Monitoring

Access the FSM dashboard at `/fsm` to monitor:

- Current FSM state and stage
- Worker status and statistics
- Recent run history
- Configuration parameters

### Configuration Updates

1. Navigate to the FSM Dashboard
2. Click "Edit Config" button
3. Modify parameters as needed
4. Click "Save Changes"

### API Endpoints

- **`GET /api/fsm/status`**: Current FSM status
- **`GET /api/fsm/runs`**: Recent FSM runs
- **`GET /api/fsm/config`**: Current configuration
- **`PUT /api/fsm/config`**: Update configuration

## Testing

Run the FSM test suite:

```bash
cd Vulcan_Sentinel
python test_fsm.py
```

This tests:
- FSM logic and state transitions
- Worker service initialization
- Database integration
- Configuration management

## Integration with Existing System

### Coexistence

- FSM runs alongside existing Modbus poller
- No interference with current data collection
- Uses existing database schema for readings
- Maintains backward compatibility

### Data Sources

Currently, the FSM reads from the existing database:
- Temperature readings from `readings` table
- Setpoint values from `setpoints` table

**Future Enhancement**: Direct Modbus reading for real-time FSM processing

### Report Generation

The FSM automatically triggers reports when:
- All stages complete successfully (full report)
- Quiet timeout occurs (partial report)
- Fault conditions are detected

**Integration Point**: The existing `ReportGenerator` class will be extended to handle automatic report generation.

## Expansion to 3 Controllers

### Current Test Bed (2 Controllers)

- **Preheat**: Enabled and monitored
- **Main Heat**: Enabled and monitored
- **Rib Heat**: Disabled (will be enabled in production)

### Production Setup (3 Controllers)

- All three controllers will be enabled
- FSM logic automatically handles missing sensors
- Configuration remains the same
- No code changes required

## Troubleshooting

### Common Issues

1. **FSM Worker Not Starting**
   - Check database permissions
   - Verify configuration files
   - Review application logs

2. **State Transitions Not Working**
   - Verify temperature tolerance settings
   - Check setpoint change thresholds
   - Review timing parameters

3. **Database Errors**
   - Ensure FSM tables are created
   - Check database connection
   - Verify schema compatibility

### Logging

FSM operations are logged with the `src.fsm_worker` and `src.fsm_logic` loggers. Check the application logs for detailed information.

### Performance

- **Sampling Rate**: 2 seconds (configurable)
- **Memory Usage**: Minimal (bounded queues)
- **CPU Impact**: Low (efficient state machine)
- **Database Load**: Moderate (state updates every 2 seconds)

## Future Enhancements

1. **Direct Modbus Integration**: Real-time reading for faster response
2. **Advanced Analytics**: Machine learning for parameter optimization
3. **Multi-Line Support**: Multiple production lines
4. **Notification System**: Email/SMS alerts for process events
5. **Historical Analysis**: Trend analysis and predictive maintenance

## Support

For issues or questions about the FSM implementation:

1. Check the application logs
2. Review this documentation
3. Run the test suite
4. Check the FSM dashboard status

The FSM system is designed to be robust and self-healing, automatically resetting to IDLE state on errors and continuing operation.
