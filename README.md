# Industrial Data Logging and Report Generation System

A comprehensive industrial data logging and report generation system designed for Helix 330 running Ubuntu Server. The system polls three Ethernet devices over Modbus TCP, logs data locally (SQLite/CSV), and generates job summary receipts via USB thermal panel-mount printer.

## Features

- **Multi-device Modbus TCP polling** - Simultaneous data collection from 3 sensor devices
- **Local data storage** - SQLite database and CSV file logging
- **Thermal printer integration** - USB thermal printer support for job receipts
- **Docker containerization** - Easy deployment and updates
- **REST API** - Web interface for data access and configuration
- **Report generation** - Automated CSV and PDF report creation
- **Git-based deployment** - Version control and automated updates

## System Architecture

```
Vulcan_Sentinel/
├── src/                    # Python source code
│   ├── modbus_poller.py    # Modbus TCP polling service
│   ├── database.py         # SQLite database operations
│   ├── printer_service.py  # Thermal printer integration
│   ├── api_server.py       # REST API server
│   └── report_generator.py # Report generation service
├── config/                 # Configuration files
│   ├── devices.yaml        # Device register maps
│   ├── printer_config.yaml # Printer configuration
│   └── app_config.yaml     # Application settings
├── docker/                 # Docker configuration
│   ├── Dockerfile          # Main application Dockerfile
│   └── docker-compose.yml  # Multi-service orchestration
├── tests/                  # Unit and integration tests
├── logs/                   # Runtime logs (git-ignored)
├── reports/                # Generated reports (git-ignored)
├── scripts/                # Deployment scripts
└── .env                    # Environment variables
```

## Prerequisites

- Ubuntu Server 20.04+ (Helix 330)
- Docker and Docker Compose
- Git
- USB thermal printer (compatible with CUPS)
- Network access to Modbus TCP devices

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Vulcan_Sentinel
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
# Edit .env with your device IPs and settings
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

- **API Dashboard**: http://localhost:8080
- **Data Logs**: Check `logs/` directory
- **Reports**: Check `reports/` directory

## Configuration

### Device Configuration

Edit `config/devices.yaml` to configure your Modbus devices:

```yaml
devices:
  sensor_1:
    name: "Temperature Sensor 1"
    ip: "169.254.1.1"
    port: 502
    slave_id: 1
    registers:
      temperature: 402
      pressure: 404
      flow_rate: 406
    polling_interval: 20  # seconds
```

### Printer Configuration

Edit `config/printer_config.yaml` for thermal printer settings:

```yaml
printer:
  name: "USB_Thermal_Printer"
  connection: "usb://0x0483/0x5740"
  paper_width: 80  # mm
  print_quality: "high"
  auto_cut: true
```

## Services

### 1. Modbus Poller Service

- Polls all configured Modbus devices
- Stores data in SQLite database
- Generates CSV logs
- Handles connection failures gracefully

### 2. API Server

- RESTful API for data access
- Real-time data streaming
- Configuration management
- Health monitoring

### 3. Printer Service

- Manages thermal printer connections
- Generates job receipts
- Handles print queue
- Error recovery

### 4. Report Generator

- Scheduled report generation
- CSV and PDF output formats
- Email distribution
- Archive management

## Deployment

### Initial Deployment

```bash
# Clone repository
git clone <repository-url>
cd Vulcan_Sentinel

# Configure environment
cp .env.example .env
# Edit .env with your settings

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

### Automated Updates

Use the deployment script for automated updates:

```bash
./scripts/update.sh
```

## Monitoring

### Health Checks

```bash
# Check service status
docker-compose ps

# View service logs
docker-compose logs [service_name]

# Monitor resource usage
docker stats
```

### Data Verification

```bash
# Check database
docker-compose exec app python -c "from src.database import check_data; check_data()"

# Verify CSV logs
ls -la logs/

# Check printer status
docker-compose exec printer python -c "from src.printer_service import check_printer; check_printer()"
```

## Troubleshooting

### Common Issues

1. **Modbus Connection Failures**
   - Verify device IP addresses
   - Check network connectivity
   - Confirm Modbus register addresses

2. **Printer Issues**
   - Verify USB connection
   - Check CUPS printer configuration
   - Test printer with simple print job

3. **Database Errors**
   - Check disk space
   - Verify file permissions
   - Review database logs

### Log Analysis

```bash
# View application logs
tail -f logs/app.log

# View Docker logs
docker-compose logs -f [service_name]

# Check system resources
htop
df -h
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
pytest tests/

# Run locally
python src/main.py
```

### Testing

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run with coverage
pytest --cov=src tests/
```

## License

[Add your license information here]

## Support

For technical support or questions, please contact [your contact information]. 