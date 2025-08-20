"""
Database Manager for SQLite Operations

Handles all database operations including data storage,
retrieval, and management for the industrial data logging system.
"""

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import os
import pytz

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database operations"""
    
    def __init__(self, db_path: str = "data/vulcan_sentinel.db"):
        self.db_path = db_path
        self._ensure_data_directory()
        self._init_connection()
        
        # Set timezone to CST to match other components
        self.cst_tz = pytz.timezone('America/Chicago')
    
    def _ensure_data_directory(self):
        """Ensure the data directory exists"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
    
    def _init_connection(self):
        """Initialize database connection"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row  # Enable dict-like access
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def create_tables(self):
        """Create all necessary database tables"""
        try:
            cursor = self.conn.cursor()
            
            # Create devices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    ip_address TEXT NOT NULL,
                    port INTEGER NOT NULL DEFAULT 502,
                    slave_id INTEGER NOT NULL DEFAULT 1,
                    register_address INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create new simplified readings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    timestamp TIME NOT NULL,
                    preheat REAL,
                    main_heat REAL,
                    rib_heat REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create setpoints table for storing temperature setpoints
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS setpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    setpoint_value REAL NOT NULL,
                    deviation REAL DEFAULT 5.0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(device_name)
                )
            """)
            
            # Create events table for system events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    device_name TEXT,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_date_timestamp 
                ON readings (date, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_date 
                ON readings (date)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                ON events (timestamp)
            """)
            
            self.conn.commit()
            logger.info("Database tables created successfully")
            
            # Initialize default setpoints if table is empty
            cursor.execute("SELECT COUNT(*) FROM setpoints")
            if cursor.fetchone()[0] == 0:
                logger.info("Initializing default setpoints")
                self.store_setpoint("preheat", 150.0, None)  # Deviation will be calculated dynamically
                self.store_setpoint("main_heat", 200.0, None)  # Deviation will be calculated dynamically
                self.store_setpoint("rib_heat", 175.0, None)  # Deviation will be calculated dynamically
            else:
                logger.info("Setpoints table already has data")
            
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def store_readings(self, device_name: str, timestamp: datetime, readings: Dict[str, float]):
        """Store readings for a device in the new format"""
        try:
            cursor = self.conn.cursor()
            
            # Convert timestamp to CST and extract date and time
            cst_timestamp = timestamp.astimezone(self.cst_tz)
            date_str = cst_timestamp.strftime('%Y-%m-%d')
            time_str = cst_timestamp.strftime('%H:%M:%S')
            
            # Check if we already have a reading for this exact timestamp
            cursor.execute("""
                SELECT id FROM readings 
                WHERE date = ? AND timestamp = ?
            """, (date_str, time_str))
            
            existing = cursor.fetchone()
            
            # Extract the temperature value from the readings dict
            # The readings dict contains {'temperature': value} for each device
            temperature_value = readings.get('temperature')
            
            if existing:
                # Update existing record - only update the column for this specific device
                if device_name == 'preheat':
                    cursor.execute("""
                        UPDATE readings 
                        SET preheat = ?
                        WHERE date = ? AND timestamp = ?
                    """, (temperature_value, date_str, time_str))
                elif device_name == 'main_heat':
                    cursor.execute("""
                        UPDATE readings 
                        SET main_heat = ?
                        WHERE date = ? AND timestamp = ?
                    """, (temperature_value, date_str, time_str))
                elif device_name == 'rib_heat':
                    cursor.execute("""
                        UPDATE readings 
                        SET rib_heat = ?
                        WHERE date = ? AND timestamp = ?
                    """, (temperature_value, date_str, time_str))
            else:
                # Insert new record - only set the column for this specific device
                if device_name == 'preheat':
                    cursor.execute("""
                        INSERT INTO readings (date, timestamp, preheat, main_heat, rib_heat)
                        VALUES (?, ?, ?, NULL, NULL)
                    """, (date_str, time_str, temperature_value))
                elif device_name == 'main_heat':
                    cursor.execute("""
                        INSERT INTO readings (date, timestamp, preheat, main_heat, rib_heat)
                        VALUES (?, ?, NULL, ?, NULL)
                    """, (date_str, time_str, temperature_value))
                elif device_name == 'rib_heat':
                    cursor.execute("""
                        INSERT INTO readings (date, timestamp, preheat, main_heat, rib_heat)
                        VALUES (?, ?, NULL, NULL, ?)
                    """, (date_str, time_str, temperature_value))
            
            self.conn.commit()
            logger.debug(f"Stored readings for {device_name} at {date_str} {time_str}")
            
        except Exception as e:
            logger.error(f"Failed to store readings for {device_name}: {e}")
            self.conn.rollback()
            raise
    
    def get_latest_readings(self, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the latest readings for all devices or a specific device using new schema"""
        try:
            cursor = self.conn.cursor()
            
            if device_name:
                # Get latest reading for specific device
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE date = (
                        SELECT MAX(date) FROM readings
                    ) AND timestamp = (
                        SELECT MAX(timestamp) FROM readings WHERE date = (
                            SELECT MAX(date) FROM readings
                        )
                    )
                """)
                
                row = cursor.fetchone()
                if row:
                    date_str, time_str, preheat, main_heat, rib_heat = row
                    
                    # Extract temperature for the specific device
                    temperature = None
                    if device_name == 'preheat':
                        temperature = preheat
                    elif device_name == 'main_heat':
                        temperature = main_heat
                    elif device_name == 'rib_heat':
                        temperature = rib_heat
                    
                    if temperature is not None:
                        timestamp_str = f"{date_str} {time_str}"
                        result = {
                            'device_name': device_name,
                            'register_name': 'temperature',
                            'value': temperature,
                            'timestamp': timestamp_str,
                            'date': date_str,
                            'time': time_str
                        }
                        return [result]
            else:
                # Get latest readings for all devices
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE date = (
                        SELECT MAX(date) FROM readings
                    ) AND timestamp = (
                        SELECT MAX(timestamp) FROM readings WHERE date = (
                            SELECT MAX(date) FROM readings
                        )
                    )
                """)
                
                row = cursor.fetchone()
                if row:
                    date_str, time_str, preheat, main_heat, rib_heat = row
                    timestamp_str = f"{date_str} {time_str}"
                    
                    results = []
                    
                    # Create results for each device that has data
                    if preheat is not None:
                        results.append({
                            'device_name': 'preheat',
                            'register_name': 'temperature',
                            'value': preheat,
                            'timestamp': timestamp_str,
                            'date': date_str,
                            'time': time_str
                        })
                    
                    if main_heat is not None:
                        results.append({
                            'device_name': 'main_heat',
                            'register_name': 'temperature',
                            'value': main_heat,
                            'timestamp': timestamp_str,
                            'date': date_str,
                            'time': time_str
                        })
                    
                    if rib_heat is not None:
                        results.append({
                            'device_name': 'rib_heat',
                            'register_name': 'temperature',
                            'value': rib_heat,
                            'timestamp': timestamp_str,
                            'date': date_str,
                            'time': time_str
                        })
                    
                    return results
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to get latest readings: {e}")
            return []
    
    def get_readings_range(self, device_name: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get readings for a device within a time range using new schema"""
        try:
            cursor = self.conn.cursor()
            
            # Convert timezone-aware datetime objects to naive datetime objects for database comparison
            # since the database stores naive datetime strings
            if start_time.tzinfo is not None:
                start_time = start_time.replace(tzinfo=None)
            if end_time.tzinfo is not None:
                end_time = end_time.replace(tzinfo=None)
            
            logger.info(f"Querying database for {device_name} from {start_time} to {end_time}")
            
            # Convert datetime objects to date and time strings for the new schema
            start_date = start_time.strftime('%Y-%m-%d')
            start_time_str = start_time.strftime('%H:%M:%S')
            end_date = end_time.strftime('%Y-%m-%d')
            end_time_str = end_time.strftime('%H:%M:%S')
            
            # Query based on the new schema with date and timestamp columns
            if start_date == end_date:
                # Same day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE date = ? AND timestamp BETWEEN ? AND ?
                    ORDER BY date ASC, timestamp ASC
                """, (start_date, start_time_str, end_time_str))
            else:
                # Cross-day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE (date > ? OR (date = ? AND timestamp >= ?))
                    AND (date < ? OR (date = ? AND timestamp <= ?))
                    ORDER BY date ASC, timestamp ASC
                """, (start_date, start_date, start_time_str, end_date, end_date, end_time_str))
            
            results = []
            for row in cursor.fetchall():
                date_str, time_str, preheat, main_heat, rib_heat = row
                
                # Create a result dict that matches the expected format
                # Extract the temperature value for the specific device
                temperature = None
                if device_name == 'preheat':
                    temperature = preheat
                elif device_name == 'main_heat':
                    temperature = main_heat
                elif device_name == 'rib_heat':
                    temperature = rib_heat
                
                if temperature is not None:
                    # Create a timestamp string that combines date and time
                    timestamp_str = f"{date_str} {time_str}"
                    
                    # Create a result dict that matches the old schema format
                    result = {
                        'device_name': device_name,
                        'register_name': 'temperature',
                        'value': temperature,
                        'timestamp': timestamp_str,
                        'date': date_str,
                        'time': time_str
                    }
                    results.append(result)
            
            logger.info(f"Database query returned {len(results)} results for {device_name}")
            
            # Log a few sample timestamps if we have results
            if results:
                logger.info(f"Sample timestamps: {results[0]['timestamp']} to {results[-1]['timestamp']}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get readings range for {device_name}: {e}")
            return []
    
    def get_statistics(self, device_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get statistical data for a device over the specified hours"""
        try:
            cursor = self.conn.cursor()
            end_time = datetime.now(self.cst_tz)
            start_time = end_time - timedelta(hours=hours)
            
            # Convert timezone-aware datetime objects to naive datetime objects for database comparison
            if start_time.tzinfo is not None:
                start_time = start_time.replace(tzinfo=None)
            if end_time.tzinfo is not None:
                end_time = end_time.replace(tzinfo=None)
            
            cursor.execute("""
                SELECT 
                    register_name,
                    COUNT(*) as count,
                    AVG(value) as avg_value,
                    MIN(value) as min_value,
                    MAX(value) as max_value,
                    STDDEV(value) as std_dev
                FROM readings
                WHERE device_name = ? AND timestamp BETWEEN ? AND ?
                GROUP BY register_name
            """, (device_name, start_time, end_time))
            
            stats = {}
            for row in cursor.fetchall():
                register_name = row['register_name']
                stats[register_name] = {
                    'count': row['count'],
                    'average': row['avg_value'],
                    'minimum': row['min_value'],
                    'maximum': row['max_value'],
                    'std_dev': row['std_dev']
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics for {device_name}: {e}")
            return {}
    
    def log_event(self, event_type: str, message: str, severity: str = "INFO", device_name: Optional[str] = None):
        """Log a system event"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (event_type, device_name, message, severity)
                VALUES (?, ?, ?, ?)
            """, (event_type, device_name, message, severity))
            
            self.conn.commit()
            logger.debug(f"Logged event: {event_type} - {message}")
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
    
    def get_events(self, limit: int = 100, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent system events"""
        try:
            cursor = self.conn.cursor()
            
            if severity:
                cursor.execute("""
                    SELECT * FROM events
                    WHERE severity = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (severity, limit))
            else:
                cursor.execute("""
                    SELECT * FROM events
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
            
            results = []
            for row in cursor.fetchall():
                results.append(dict(row))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return []
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old data to prevent database bloat"""
        try:
            cursor = self.conn.cursor()
            cutoff_date = datetime.now(self.cst_tz) - timedelta(days=days)
            
            # Delete old readings
            cursor.execute("""
                DELETE FROM readings
                WHERE timestamp < ?
            """, (cutoff_date,))
            
            readings_deleted = cursor.rowcount
            
            # Delete old events (keep more recent events)
            event_cutoff = datetime.now(self.cst_tz) - timedelta(days=7)
            cursor.execute("""
                DELETE FROM events
                WHERE timestamp < ?
            """, (event_cutoff,))
            
            events_deleted = cursor.rowcount
            
            self.conn.commit()
            
            logger.info(f"Cleanup completed: {readings_deleted} readings, {events_deleted} events deleted")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            self.conn.rollback()
    
    def store_setpoint(self, device_name: str, setpoint_value: float, deviation: float = None):
        """Store or update setpoint for a device"""
        try:
            cursor = self.conn.cursor()
            
            # If deviation is None, don't update the existing deviation value
            if deviation is None:
                cursor.execute("""
                    INSERT OR REPLACE INTO setpoints (device_name, setpoint_value, timestamp)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (device_name, setpoint_value))
                logger.debug(f"Stored setpoint for {device_name}: {setpoint_value}°F (deviation unchanged)")
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO setpoints (device_name, setpoint_value, deviation, timestamp)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (device_name, setpoint_value, deviation))
                logger.debug(f"Stored setpoint for {device_name}: {setpoint_value}°F ±{deviation}°F")
            
            self.conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to store setpoint for {device_name}: {e}")
            self.conn.rollback()
            raise
    
    def get_setpoint(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest setpoint for a device"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT setpoint_value, deviation, timestamp
                FROM setpoints
                WHERE device_name = ?
            """, (device_name,))
            
            row = cursor.fetchone()
            if row:
                setpoint_value, deviation, timestamp = row
                return {
                    'setpoint_value': setpoint_value,
                    'deviation': deviation,
                    'timestamp': timestamp
                }
            return None
            
        except Exception as e:
            logger.error(f"Failed to get setpoint for {device_name}: {e}")
            return None
    
    def get_all_setpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get all setpoints for all devices"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT device_name, setpoint_value, deviation, timestamp
                FROM setpoints
            """)
            
            setpoints = {}
            for row in cursor.fetchall():
                device_name, setpoint_value, deviation, timestamp = row
                setpoints[device_name] = {
                    'setpoint_value': setpoint_value,
                    'deviation': deviation,
                    'timestamp': timestamp
                }
            
            return setpoints
            
        except Exception as e:
            logger.error(f"Failed to get all setpoints: {e}")
            return {}
    
    def update_setpoint_deviation(self, device_name: str, deviation: float):
        """Update the deviation for an existing setpoint"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                UPDATE setpoints 
                SET deviation = ?, timestamp = CURRENT_TIMESTAMP
                WHERE device_name = ?
            """, (deviation, device_name))
            
            if cursor.rowcount > 0:
                self.conn.commit()
                logger.debug(f"Updated deviation for {device_name}: ±{deviation}°F")
                return True
            else:
                logger.warning(f"No setpoint found for {device_name} to update deviation")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update deviation for {device_name}: {e}")
            self.conn.rollback()
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database statistics and information"""
        try:
            cursor = self.conn.cursor()
            
            # Get table sizes
            cursor.execute("SELECT COUNT(*) FROM readings")
            readings_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM events")
            events_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM setpoints")
            setpoints_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT device_name) FROM readings")
            devices_count = cursor.fetchone()[0]
            
            # Get database file size
            file_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            return {
                'readings_count': readings_count,
                'events_count': events_count,
                'setpoints_count': setpoints_count,
                'devices_count': devices_count,
                'file_size_mb': round(file_size / (1024 * 1024), 2),
                'database_path': self.db_path
            }
            
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {}
    
    def get_readings_for_period(self, device_name: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """
        Get temperature readings for a specific device during a time period.
        
        Args:
            device_name: Name of the device (e.g., 'preheat', 'main_heat', 'rib_heat')
            start_time: Start time of the period
            end_time: End time of the period
            
        Returns:
            List of dictionaries containing temperature readings
        """
        try:
            cursor = self.conn.cursor()
            
            # Convert datetime objects to string format for database query
            start_date = start_time.strftime('%Y-%m-%d')
            start_timestamp = start_time.strftime('%H:%M:%S')
            end_date = end_time.strftime('%Y-%m-%d')
            end_timestamp = end_time.strftime('%H:%M:%S')
            
            # Query readings within the time period
            if start_date == end_date:
                # Same day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE date = ? AND timestamp BETWEEN ? AND ?
                    ORDER BY date, timestamp
                """, (start_date, start_timestamp, end_timestamp))
            else:
                # Cross-day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE (date = ? AND timestamp >= ?) OR 
                          (date > ? AND date < ?) OR
                          (date = ? AND timestamp <= ?)
                    ORDER BY date, timestamp
                """, (start_date, start_timestamp, start_date, end_date, end_date, end_timestamp))
            
            readings = []
            for row in cursor.fetchall():
                date_str, time_str, preheat, main_heat, rib_heat = row
                
                # Extract temperature for the specific device
                temperature = None
                if device_name == 'preheat':
                    temperature = preheat
                elif device_name == 'main_heat':
                    temperature = main_heat
                elif device_name == 'rib_heat':
                    temperature = rib_heat
                
                if temperature is not None:
                    readings.append({
                        device_name: temperature,
                        'timestamp': f"{date_str} {time_str}",
                        'date': date_str,
                        'time': time_str
                    })
            
            logger.debug(f"Retrieved {len(readings)} readings for {device_name} between {start_time} and {end_time}")
            return readings
            
        except Exception as e:
            logger.error(f"Failed to get readings for period for {device_name}: {e}")
            return []
    
    def close(self):
        """Close database connection"""
        try:
            if hasattr(self, 'conn'):
                self.conn.close()
                logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
    
    def __del__(self):
        """Destructor to ensure connection is closed"""
        self.close() 