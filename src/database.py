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
                    port INTEGER NOT NULL,
                    slave_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create readings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_name TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    register_name TEXT NOT NULL,
                    value REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (device_name) REFERENCES devices (name)
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
                CREATE INDEX IF NOT EXISTS idx_readings_device_timestamp 
                ON readings (device_name, timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_readings_timestamp 
                ON readings (timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                ON events (timestamp)
            """)
            
            self.conn.commit()
            logger.info("Database tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    def store_readings(self, device_name: str, timestamp: datetime, readings: Dict[str, float]):
        """Store readings for a device"""
        try:
            cursor = self.conn.cursor()
            
            # Store each reading
            for register_name, value in readings.items():
                cursor.execute("""
                    INSERT INTO readings (device_name, timestamp, register_name, value)
                    VALUES (?, ?, ?, ?)
                """, (device_name, timestamp, register_name, value))
            
            self.conn.commit()
            logger.debug(f"Stored {len(readings)} readings for {device_name}")
            
        except Exception as e:
            logger.error(f"Failed to store readings for {device_name}: {e}")
            self.conn.rollback()
            raise
    
    def get_latest_readings(self, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the latest readings for all devices or a specific device"""
        try:
            cursor = self.conn.cursor()
            
            if device_name:
                cursor.execute("""
                    SELECT r.*, d.ip_address, d.port, d.slave_id
                    FROM readings r
                    JOIN devices d ON r.device_name = d.name
                    WHERE r.device_name = ?
                    AND r.timestamp = (
                        SELECT MAX(timestamp) 
                        FROM readings 
                        WHERE device_name = r.device_name
                    )
                    ORDER BY r.register_name
                """, (device_name,))
            else:
                cursor.execute("""
                    SELECT r.*, d.ip_address, d.port, d.slave_id
                    FROM readings r
                    JOIN devices d ON r.device_name = d.name
                    WHERE r.timestamp = (
                        SELECT MAX(timestamp) 
                        FROM readings r2 
                        WHERE r2.device_name = r.device_name
                    )
                    ORDER BY r.device_name, r.register_name
                """)
            
            results = []
            for row in cursor.fetchall():
                results.append(dict(row))
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get latest readings: {e}")
            return []
    
    def get_readings_range(self, device_name: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get readings for a device within a time range"""
        try:
            cursor = self.conn.cursor()
            
            logger.info(f"Querying database for {device_name} from {start_time} to {end_time}")
            
            cursor.execute("""
                SELECT * FROM readings
                WHERE device_name = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            """, (device_name, start_time, end_time))
            
            results = []
            for row in cursor.fetchall():
                results.append(dict(row))
            
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
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database statistics and information"""
        try:
            cursor = self.conn.cursor()
            
            # Get table sizes
            cursor.execute("SELECT COUNT(*) FROM readings")
            readings_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM events")
            events_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(DISTINCT device_name) FROM readings")
            devices_count = cursor.fetchone()[0]
            
            # Get database file size
            file_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            return {
                'readings_count': readings_count,
                'events_count': events_count,
                'devices_count': devices_count,
                'file_size_mb': round(file_size / (1024 * 1024), 2),
                'database_path': self.db_path
            }
            
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {}
    
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