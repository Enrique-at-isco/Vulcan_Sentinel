#!/usr/bin/env python3
"""
Debug script to check timestamp formats in the database
"""

import sqlite3
import os
from datetime import datetime
import pytz

def check_timestamps():
    """Check the format of timestamps in the database"""
    
    db_path = "data/vulcan_sentinel.db"
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get latest readings for each device
        cursor.execute("""
            SELECT device_name, value, timestamp, typeof(timestamp)
            FROM readings r1
            WHERE register_name = 'temperature'
            AND timestamp = (
                SELECT MAX(timestamp) 
                FROM readings r2 
                WHERE r2.device_name = r1.device_name 
                AND r2.register_name = 'temperature'
            )
        """)
        
        print("Latest temperature readings:")
        print("=" * 80)
        
        for row in cursor.fetchall():
            device_name, value, timestamp, timestamp_type = row
            print(f"Device: {device_name}")
            print(f"Temperature: {value}°F")
            print(f"Timestamp: {timestamp}")
            print(f"Timestamp type: {timestamp_type}")
            print(f"Timestamp repr: {repr(timestamp)}")
            print("-" * 40)
        
        # Also check a few recent readings
        cursor.execute("""
            SELECT device_name, timestamp, typeof(timestamp)
            FROM readings
            WHERE register_name = 'temperature'
            ORDER BY timestamp DESC
            LIMIT 10
        """)
        
        print("\nRecent timestamps:")
        print("=" * 80)
        
        for row in cursor.fetchall():
            device_name, timestamp, timestamp_type = row
            print(f"{device_name}: {timestamp} (type: {timestamp_type})")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_timestamps()
