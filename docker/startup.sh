#!/bin/bash

# Fix permissions for mounted volumes
echo "Fixing permissions for mounted volumes..."
chmod 755 /app/logs /app/reports /app/data 2>/dev/null || true
touch /app/logs/app.log /app/logs/modbus_poller.log 2>/dev/null || true
chmod 666 /app/logs/*.log 2>/dev/null || true

# Start the application
echo "Starting Vulcan Sentinel..."
exec python src/main.py 