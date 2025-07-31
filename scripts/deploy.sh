#!/bin/bash

# Vulcan Sentinel - Initial Deployment Script
# This script handles the initial setup and deployment of the system

set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/your-username/vulcan-sentinel.git"
BRANCH="main"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install package
install_package() {
    local package=$1
    if command_exists apt-get; then
        sudo apt-get update && sudo apt-get install -y "$package"
    elif command_exists yum; then
        sudo yum install -y "$package"
    elif command_exists dnf; then
        sudo dnf install -y "$package"
    else
        error "Unsupported package manager. Please install $package manually."
        return 1
    fi
}

log "Starting Vulcan Sentinel deployment..."

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    error "Please do not run this script as root. Use a regular user with sudo privileges."
    exit 1
fi

# Check and install system dependencies
info "Checking system dependencies..."

# Check for Git
if ! command_exists git; then
    warning "Git not found. Installing..."
    install_package git
fi

# Check for Docker
if ! command_exists docker; then
    warning "Docker not found. Installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    rm get-docker.sh
    warning "Docker installed. Please log out and back in, then run this script again."
    exit 0
fi

# Check for Docker Compose
if ! command_exists docker-compose; then
    warning "Docker Compose not found. Installing..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create application directory
APP_DIR="/opt/vulcan-sentinel"
if [ ! -d "$APP_DIR" ]; then
    log "Creating application directory..."
    sudo mkdir -p "$APP_DIR"
    sudo chown "$USER:$USER" "$APP_DIR"
fi

# Clone repository
if [ ! -d "$APP_DIR/.git" ]; then
    log "Cloning repository..."
    git clone -b "$BRANCH" "$REPO_URL" "$APP_DIR"
else
    log "Repository already exists. Pulling latest changes..."
    cd "$APP_DIR"
    git pull origin "$BRANCH"
fi

cd "$APP_DIR"

# Create necessary directories
log "Creating necessary directories..."
mkdir -p logs reports data backups

# Set up environment file
if [ ! -f .env ]; then
    log "Setting up environment file..."
    cp env.example .env
    warning "Please edit .env file with your specific configuration before continuing."
    echo "Press Enter when you have configured the .env file..."
    read -r
fi

# Create default configuration files
log "Creating default configuration files..."
python3 -c "
from src.config_manager import ConfigManager
config_manager = ConfigManager()
config_manager.create_default_configs()
print('Default configuration files created.')
"

# Build and start services
log "Building Docker images..."
docker-compose build

log "Starting services..."
docker-compose up -d

# Wait for services to start
log "Waiting for services to start..."
sleep 30

# Check service status
log "Checking service status..."
if docker-compose ps | grep -q "unhealthy\|restarting"; then
    error "Some services failed to start properly."
    docker-compose logs
    exit 1
fi

# Set up systemd service for auto-start
log "Setting up systemd service for auto-start..."
sudo tee /etc/systemd/system/vulcan-sentinel.service > /dev/null <<EOF
[Unit]
Description=Vulcan Sentinel
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/docker-compose up -d
ExecStop=/usr/local/bin/docker-compose down
User=$USER
Group=$USER

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable vulcan-sentinel.service
sudo systemctl start vulcan-sentinel.service

# Set up log rotation
log "Setting up log rotation..."
sudo tee /etc/logrotate.d/vulcan-sentinel > /dev/null <<EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
    postrotate
        systemctl reload vulcan-sentinel.service
    endscript
}
EOF

# Set up firewall rules (if ufw is available)
if command_exists ufw; then
    log "Setting up firewall rules..."
    sudo ufw allow 8080/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
fi

# Create monitoring script
log "Creating monitoring script..."
tee scripts/monitor.sh > /dev/null <<'EOF'
#!/bin/bash
# Simple monitoring script for Vulcan Sentinel

APP_DIR="/opt/vulcan-sentinel"
cd "$APP_DIR"

echo "=== Vulcan Sentinel Status ==="
echo "Time: $(date)"
echo

echo "=== Docker Services ==="
docker-compose ps
echo

echo "=== Recent Logs ==="
tail -n 20 logs/app.log 2>/dev/null || echo "No app logs found"
echo

echo "=== System Resources ==="
df -h | grep -E "(Filesystem|/dev/)"
echo

echo "=== Memory Usage ==="
free -h
echo

echo "=== Network Connections ==="
netstat -tlnp | grep -E "(8080|80|443)" || echo "No web services found"
EOF

chmod +x scripts/monitor.sh

# Create backup script
log "Creating backup script..."
tee scripts/backup.sh > /dev/null <<'EOF'
#!/bin/bash
# Backup script for Vulcan Sentinel

APP_DIR="/opt/vulcan-sentinel"
BACKUP_DIR="$APP_DIR/backups"
BACKUP_NAME="backup_$(date +'%Y%m%d_%H%M%S')"

cd "$APP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"

# Stop services
docker-compose down

# Backup data
cp -r data/ "$BACKUP_DIR/$BACKUP_NAME/"
cp -r config/ "$BACKUP_DIR/$BACKUP_NAME/"
cp docker-compose.yml "$BACKUP_DIR/$BACKUP_NAME/"
cp .env "$BACKUP_DIR/$BACKUP_NAME/"

# Restart services
docker-compose up -d

# Cleanup old backups (keep last 10)
cd "$BACKUP_DIR"
ls -t | tail -n +11 | xargs -r rm -rf

echo "Backup completed: $BACKUP_DIR/$BACKUP_NAME"
EOF

chmod +x scripts/backup.sh

# Final status check
log "Performing final status check..."
sleep 10

if curl -f -s http://localhost:8080/health > /dev/null; then
    log "✅ Deployment completed successfully!"
    echo
    echo "=== System Information ==="
    echo "Application URL: http://localhost:8080"
    echo "Application Directory: $APP_DIR"
    echo "Logs Directory: $APP_DIR/logs"
    echo "Reports Directory: $APP_DIR/reports"
    echo
    echo "=== Useful Commands ==="
    echo "Check status: $APP_DIR/scripts/monitor.sh"
    echo "View logs: docker-compose logs -f"
    echo "Backup: $APP_DIR/scripts/backup.sh"
    echo "Update: $APP_DIR/scripts/update.sh"
    echo "Stop services: docker-compose down"
    echo "Start services: docker-compose up -d"
    echo
    echo "=== Systemd Service ==="
    echo "Enable auto-start: sudo systemctl enable vulcan-sentinel.service"
    echo "Disable auto-start: sudo systemctl disable vulcan-sentinel.service"
    echo "Start service: sudo systemctl start vulcan-sentinel.service"
    echo "Stop service: sudo systemctl stop vulcan-sentinel.service"
    echo "Check status: sudo systemctl status vulcan-sentinel.service"
else
    warning "⚠️  Deployment completed, but API health check failed."
    echo "Please check the logs: docker-compose logs"
fi

log "Deployment script completed!" 