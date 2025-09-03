# Vulcan Sentinel - Industrial Heating Process Monitoring & Auto-Reporting System

A comprehensive industrial data logging, monitoring, and automatic report generation system designed for multi-stage heating processes. The system polls PM PLUS controllers over Modbus TCP, implements a Finite State Machine (FSM) for automatic stage detection, and generates comprehensive reports automatically when heating cycles complete.

## Features

- **Multi-device Modbus TCP polling** - Simultaneous data collection from PM PLUS controllers (preheat, main_heat, rib_heat)
- **Finite State Machine (FSM)** - Automatic detection of heating stages (Preheat → Main Heat → Rib Heat)
- **Automatic report generation** - Triggers reports when heating cycles complete or timeout
- **Real-time monitoring** - Web dashboard with live sensor data, system status, and FSM state
- **Local data storage** - SQLite database with optimized connection pooling and WAL mode
- **Report generation** - Automated CSV and PDF reports with thermal data analysis
- **Docker containerization** - Easy deployment and updates with health monitoring
- **REST API** - Web interface for data access, configuration, and FSM management
- **Git-based deployment** - Version control and automated updates

## System Architecture

```
Vulcan_Sentinel/
├── src/                    # Python source code
│   ├── main.py            # Main application entry point
│   ├── modbus_poller.py   # Modbus TCP polling service (20s intervals)
│   ├── database.py        # SQLite database operations with FSM tables
│   ├── web_server.py      # Flask web server and API endpoints
│   ├── report_generator.py # Report generation service
│   ├── fsm_logic.py       # FSM state machine implementation
│   ├── fsm_worker.py      # FSM worker service (1-2s sampling)
│   └── config_manager.py  # Configuration management
├── config/                 # Configuration files
│   ├── devices.yaml        # PM PLUS controller register maps
│   ├── app_config.yaml     # Application settings
│   └── fsm_config.yaml     # FSM parameters and device mapping
├── templates/              # Web interface templates
│   ├── dashboard.html      # Main dashboard
│   ├── fsm_dashboard.html  # FSM monitoring and configuration
│   ├── reports.html        # Report generation page
│   └── base.html           # Base template
├── static/                 # Static web assets
│   └── js/
│       └── dashboard.js    # Dashboard JavaScript
├── docker/                 # Docker configuration
│   ├── Dockerfile          # Main application Dockerfile
│   └── docker-compose.yml  # Multi-service orchestration
├── data/                   # SQLite database and CSV logs (git-ignored)
├── logs/                   # Runtime logs (git-ignored)
├── reports/                # Generated reports (git-ignored)
├── test_fsm.py            # FSM testing script
├── FSM_README.md          # FSM implementation documentation
└── .env                    # Environment variables
```

## FSM (Finite State Machine) Overview

The system implements an intelligent FSM that automatically detects heating process stages:

### States
- **IDLE** → **PREHEAT_RAMP** → **PREHEAT_STABLE** → **PREHEAT_END**
- **MAIN_RAMP** → **MAIN_STABLE** → **MAIN_END**
- **RIB_RAMP** → **RIB_STABLE** → **RIB_END** → **REPORT**

### Key Features
- **Automatic stage detection** based on temperature ramping and setpoint changes
- **Real-time statistics** using Welford's method for online mean/standard deviation
- **Configurable parameters** for tolerance bands, ramp detection, and timeouts
- **Fault handling** with automatic stage termination and reporting
- **Partial reporting** when cycles don't complete all stages

## Prerequisites

- Ubuntu Server 20.04+ (Helix 330) or Windows 10+
- Docker and Docker Compose
- Git
- Network access to PM PLUS controllers
- Modern web browser for dashboard access

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Enrique-at-isco/Vulcan_Sentinel
cd Vulcan_Sentinel
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
# Edit .env with your PM PLUS controller IPs and settings
```

### 3. Build and Run

```bash
# Build Docker images
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f
```

### 4. Access the System

- **Main Dashboard**: http://localhost:8080
- **FSM Dashboard**: http://localhost:8080/fsm
- **Reports**: http://localhost:8080/reports
- **API Endpoints**: http://localhost:8080/api/*

## Configuration

### PM PLUS Controller Configuration

Edit `config/devices.yaml` to configure your PM PLUS controllers:

```yaml
devices:
  preheat:
    name: "Preheat Controller"
    ip: "169.254.100.100"
    port: 502
    slave_id: 1
    registers:
      temperature: 402        # Filtered Process Value
      setpoint_register: 2172 # Active Closed-Loop Set Point
    polling_interval: 20     # seconds
  
  main_heat:
    name: "Main Heat Controller"
    ip: "169.254.100.200"
    port: 502
    slave_id: 1
    registers:
      temperature: 402
      setpoint_register: 2172
    polling_interval: 20
```

### FSM Configuration

Edit `config/fsm_config.yaml` for FSM parameters:

```yaml
sampling_period_s: 1.0        # FSM sampling rate
Tol_F: 8                      # Temperature tolerance band
DeltaRamp_F: 20              # Minimum temperature rise for ramp detection
dT_min_F_per_min: 10         # Minimum ramp rate
T_stable_s: 90               # Time in tolerance band to mark stable
Max_ramp_s: 900              # Maximum ramp time per stage
Max_stage_s: 7200            # Maximum stage duration
```

## Services

### 1. Modbus Poller Service

- Polls PM PLUS controllers every 20 seconds
- Reads temperature and setpoint registers
- Stores data in SQLite database
- Generates CSV logs with automatic cleanup
- Handles connection failures gracefully

### 2. FSM Worker Service

- Runs FSM logic at 1-2 second intervals
- Detects heating stage transitions automatically
- Calculates real-time statistics during stable periods
- Triggers automatic report generation
- Persists FSM state and run history

### 3. Web Server

- Flask-based web interface
- Real-time dashboard with live sensor data
- FSM monitoring and configuration
- Report generation interface
- REST API endpoints for data access

### 4. Report Generator

- Automatic report generation on FSM completion
- Manual report generation via web interface
- CSV and PDF output formats
- Thermal data analysis and visualization
- Duration formatting in HH:MM:SS format

## FSM API Endpoints

### FSM Status and Control

```bash
# Get FSM worker status and current state
GET /api/fsm/status

# Get FSM configuration
GET /api/fsm/config

# Update FSM configuration
PUT /api/fsm/config

# Get FSM run history
GET /api/fsm/runs?line_id=621&limit=50
```

### Data Access

```bash
# Get latest sensor readings
GET /api/readings

# Get historical data
GET /api/historical?start=2025-01-01&end=2025-01-02

# Get system status
GET /api/status

# Export CSV data
GET /api/export?start=2025-01-01&end=2025-01-02
```

## Deployment

### Initial Deployment

```bash
# Clone repository
git clone https://github.com/Enrique-at-isco/Vulcan_Sentinel
cd Vulcan_Sentinel

# Configure environment
cp .env.example .env
# Edit .env with your PM PLUS controller IPs

# Build and start
docker-compose up -d

# Verify services
docker-compose ps
```

### Updates

```bash
# Pull latest changes
git pull origin main

# Rebuild and restart services
docker-compose down
docker-compose build
docker-compose up -d

# Verify update
docker-compose logs -f
```

## Testing

### FSM Testing

```bash
# Test FSM implementation
python test_fsm.py

# Test FSM logic, worker, and database integration
python -m pytest test_fsm.py -v
```

### Manual Testing

```bash
# Check database tables
docker-compose exec app python -c "from src.database import DatabaseManager; db = DatabaseManager(); print(db.get_fsm_config('test_line'))"

# Verify FSM worker status
curl http://localhost:8080/api/fsm/status
```

## Monitoring

### Health Checks

```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs -f vulcan-sentinel-app

# Monitor resource usage
docker stats
```

### FSM Monitoring

- **Dashboard**: Monitor current FSM state and recent runs
- **Logs**: Track FSM transitions and events
- **API**: Programmatic access to FSM status and configuration

## Troubleshooting

### Common Issues

1. **Modbus Connection Failures**
   - Verify PM PLUS controller IP addresses
   - Check network connectivity
   - Confirm Modbus register addresses (402, 2172)

2. **FSM Issues**
   - Check FSM worker status via `/api/fsm/status`
   - Verify FSM configuration parameters
   - Review FSM logs for state transition issues

3. **Database Errors**
   - Check disk space
   - Verify file permissions
   - Review database connection logs

### Log Analysis

```bash
# View application logs
docker-compose logs -f vulcan-sentinel-app

# View FSM-specific logs
docker-compose logs vulcan-sentinel-app | grep -i fsm

# Check system resources
docker stats
```

## Development

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
python test_fsm.py

# Run locally
python src/main.py
```

### FSM Development

The FSM system is designed for easy expansion:

- **Add new stages**: Extend the state machine in `fsm_logic.py`
- **Modify parameters**: Update `fsm_config.yaml` or use web interface
- **Add new controllers**: Update `devices.yaml` and FSM configuration
- **Custom reporting**: Extend report generation in `fsm_worker.py`

## Performance

- **Modbus polling**: 20-second intervals for archival data
- **FSM sampling**: 1-2 second intervals for real-time processing
- **Database**: SQLite with WAL mode and connection pooling
- **Memory usage**: Optimized with bounded queues and online statistics
- **Scalability**: Modular design supports expansion to additional controllers

## License

[Add your license information here]

## Support

For technical support or questions about the FSM implementation, please refer to `FSM_README.md` or contact [your contact information]. 