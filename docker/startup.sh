#!/bin/bash

# Fix permissions for mounted volumes
echo "Fixing permissions for mounted volumes..."
chmod 755 /app/logs /app/reports /app/data 2>/dev/null || true
touch /app/logs/app.log /app/logs/modbus_poller.log 2>/dev/null || true
chmod 666 /app/logs/*.log 2>/dev/null || true

# Fix database permissions
echo "Fixing database permissions..."
if [ -f /app/data/vulcan_sentinel.db ]; then
    chmod 666 /app/data/vulcan_sentinel.db 2>/dev/null || true
    echo "Database file permissions updated"
else
    echo "Database file not found, will be created by application"
fi

# Start the application
echo "Starting Vulcan Sentinel..."
exec python src/main.py 