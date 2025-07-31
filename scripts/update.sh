#!/bin/bash

# Vulcan Sentinel - Automated Update Script
# This script handles Git-based deployment and Docker service updates

set -e  # Exit on any error

# Configuration
REPO_URL="https://github.com/your-username/vulcan-sentinel.git"
BRANCH="main"
DOCKER_COMPOSE_FILE="docker-compose.yml"
BACKUP_DIR="backups"
LOG_FILE="logs/update.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

# Create necessary directories
mkdir -p "$BACKUP_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log "Starting automated update process..."

# Check if we're in a Git repository
if [ ! -d ".git" ]; then
    error "Not in a Git repository. Please clone the repository first."
    exit 1
fi

# Check if Docker and Docker Compose are available
if ! command -v docker &> /dev/null; then
    error "Docker is not installed or not in PATH"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose is not installed or not in PATH"
    exit 1
fi

# Backup current configuration
log "Creating backup of current configuration..."
BACKUP_NAME="backup_$(date +'%Y%m%d_%H%M%S')"
mkdir -p "$BACKUP_DIR/$BACKUP_NAME"

# Backup important files
cp -r config/ "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || warning "Could not backup config directory"
cp docker-compose.yml "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || warning "Could not backup docker-compose.yml"
cp .env "$BACKUP_DIR/$BACKUP_NAME/" 2>/dev/null || warning "Could not backup .env file"

log "Backup created: $BACKUP_DIR/$BACKUP_NAME"

# Fetch latest changes from remote
log "Fetching latest changes from Git..."
git fetch origin

# Check if there are updates
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/$BRANCH)

if [ "$LOCAL_COMMIT" = "$REMOTE_COMMIT" ]; then
    log "No updates available. System is up to date."
    exit 0
fi

log "Updates found. Pulling latest changes..."

# Stash any local changes
if ! git diff-index --quiet HEAD --; then
    warning "Local changes detected. Stashing changes..."
    git stash push -m "Auto-stash before update $(date)"
fi

# Pull latest changes
git pull origin $BRANCH

# Check if pull was successful
if [ $? -ne 0 ]; then
    error "Failed to pull latest changes from Git"
    exit 1
fi

log "Successfully pulled latest changes"

# Stop current services
log "Stopping current Docker services..."
docker-compose down

# Build new images
log "Building new Docker images..."
docker-compose build --no-cache

if [ $? -ne 0 ]; then
    error "Failed to build Docker images"
    log "Restoring from backup..."
    cp -r "$BACKUP_DIR/$BACKUP_NAME/"* ./
    docker-compose up -d
    exit 1
fi

# Start services
log "Starting updated services..."
docker-compose up -d

# Wait for services to be healthy
log "Waiting for services to be healthy..."
sleep 30

# Check service health
log "Checking service health..."
if docker-compose ps | grep -q "unhealthy\|restarting"; then
    error "Some services are unhealthy. Rolling back..."
    
    # Rollback to backup
    log "Rolling back to previous version..."
    docker-compose down
    cp -r "$BACKUP_DIR/$BACKUP_NAME/"* ./
    docker-compose up -d
    
    error "Rollback completed. Please check logs for issues."
    exit 1
fi

# Cleanup old backups (keep last 5)
log "Cleaning up old backups..."
cd "$BACKUP_DIR"
ls -t | tail -n +6 | xargs -r rm -rf
cd ..

# Verify update
log "Verifying update..."
sleep 10

# Check if API is responding
if curl -f -s http://localhost:8080/health > /dev/null; then
    log "Update verification successful. API is responding."
else
    warning "API health check failed, but services are running."
fi

# Show service status
log "Current service status:"
docker-compose ps

log "Update completed successfully!"
log "Backup location: $BACKUP_DIR/$BACKUP_NAME"
log "Log file: $LOG_FILE"

# Optional: Send notification
if command -v curl &> /dev/null; then
    # You can add webhook notifications here
    # curl -X POST -H "Content-Type: application/json" \
    #     -d '{"text":"Vulcan Sentinel updated successfully"}' \
    #     YOUR_WEBHOOK_URL
    :
fi

exit 0 