#!/usr/bin/env python3
"""
Debug script to check and clear setpoints table
"""

import sqlite3
import os

def check_setpoints():
    db_path = "data/vulcan_sentinel.db"
    
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current setpoints
    cursor.execute("SELECT * FROM setpoints")
    rows = cursor.fetchall()
    
    print("Current setpoints in database:")
    for row in rows:
        print(f"  {row}")
    
    # Check if we want to clear and reinitialize
    if rows:
        response = input("\nDo you want to clear and reinitialize setpoints? (y/n): ")
        if response.lower() == 'y':
            cursor.execute("DELETE FROM setpoints")
            cursor.execute("INSERT INTO setpoints (device_name, setpoint_value, deviation) VALUES (?, ?, ?)", 
                         ("preheat", 150.0, 5.0))
            cursor.execute("INSERT INTO setpoints (device_name, setpoint_value, deviation) VALUES (?, ?, ?)", 
                         ("main_heat", 200.0, 5.0))
            cursor.execute("INSERT INTO setpoints (device_name, setpoint_value, deviation) VALUES (?, ?, ?)", 
                         ("rib_heat", 175.0, 5.0))
            conn.commit()
            print("Setpoints cleared and reinitialized")
        else:
            print("Setpoints not modified")
    
    conn.close()

if __name__ == "__main__":
    check_setpoints()
