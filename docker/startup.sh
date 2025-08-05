#!/bin/bash

echo "Fixing permissions for mounted volumes..."

# Fix permissions for mounted directories
chmod 755 /app/logs /app/reports /app/data

# Fix permissions for log files if they exist
if [ -f /app/logs/modbus_poller.log ]; then
    chmod 666 /app/logs/modbus_poller.log
fi
if [ -f /app/logs/app.log ]; then
    chmod 666 /app/logs/app.log
fi

echo "Fixing database permissions..."

# Create database directory if it doesn't exist
mkdir -p /app/data

# Create database file if it doesn't exist and set permissions
touch /app/data/vulcan_sentinel.db
chmod 666 /app/data/vulcan_sentinel.db

echo "Database file permissions updated"
echo "Starting Vulcan Sentinel..."

# Start the application
exec python /app/src/main.py 