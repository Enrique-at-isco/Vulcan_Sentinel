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
        """Initialize database connection with connection pooling"""
        try:
            self.db_path = self.db_path
            logger.info(f"Database path: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database path: {e}")
            raise
    
    def _get_connection(self):
        """Get a new database connection for thread safety"""
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # Enable dict-like access
            
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Set timeout for busy database
            conn.execute("PRAGMA busy_timeout=30000")
            
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys=ON")
            
            return conn
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    def create_tables(self):
        """Create all database tables if they don't exist"""
        try:
            conn = self._get_connection()
            try:
                # Create readings table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS readings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        preheat REAL,
                        main_heat REAL,
                        rib_heat REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(date, timestamp)
                    )
                """)
                
                # Create setpoints table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS setpoints (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sensor_name TEXT NOT NULL UNIQUE,
                        setpoint_value REAL NOT NULL,
                        deviation REAL DEFAULT 5.0,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create events table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        device_name TEXT,
                        severity TEXT DEFAULT 'INFO'
                    )
                """)
                
                # Create FSM tables
                self._create_fsm_tables(conn)
                
                conn.commit()
                logger.info("Database tables created successfully")
                
            finally:
                if conn:
                    conn.close()
                    
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
            
    def _create_fsm_tables(self, conn):
        """Create FSM-specific database tables"""
        try:
            # Runtime state (1 row per line)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_runtime_state (
                    line_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL DEFAULT 'IDLE',
                    run_id TEXT,
                    stage TEXT NOT NULL DEFAULT 'none',
                    stage_enter_ts TIMESTAMP,
                    sp_ref REAL,
                    config_version INTEGER NOT NULL DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT stage_ck CHECK (stage IN ('none','preheat','main','rib'))
                )
            """)
            
            # Run header (immutable-ish)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_runs (
                    run_id TEXT PRIMARY KEY,
                    line_id TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    end_reason TEXT,
                    wo TEXT,
                    auto BOOLEAN NOT NULL DEFAULT 1,
                    preheat_ok BOOLEAN,
                    main_ok BOOLEAN,
                    rib_ok BOOLEAN,
                    preheat_flags TEXT DEFAULT '{}',
                    main_flags TEXT DEFAULT '{}',
                    rib_flags TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT end_reason_ck CHECK (end_reason IN ('normal','fault','timeout','quiet_timeout'))
                )
            """)
            
            # Per-stage stats
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_stages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    start_ts TIMESTAMP NOT NULL,
                    end_ts TIMESTAMP NOT NULL,
                    sp_start REAL,
                    sp_end REAL,
                    t_min REAL,
                    t_max REAL,
                    t_mean REAL,
                    t_std REAL,
                    status TEXT NOT NULL DEFAULT 'normal',
                    FOREIGN KEY (run_id) REFERENCES fsm_runs(run_id) ON DELETE CASCADE,
                    UNIQUE(run_id, stage, start_ts)
                )
            """)
            
            # Versioned config (JSON stored as TEXT for SQLite compatibility)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    params TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(line_id, version)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_runs_line_started ON fsm_runs (line_id, started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_runs_wo ON fsm_runs (wo)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fsm_stages_run ON fsm_stages (run_id)")
            
            # Insert default FSM config if none exists
            conn.execute("""
                INSERT OR IGNORE INTO fsm_config (line_id, version, params) VALUES 
                ('Line-07', 1, '{"sampling_period_s": 2.0, "Tol_F": 8, "DeltaRamp_F": 20, "dT_min_F_per_min": 10, "T_stable_s": 90, "DeltaOff_F": 20, "T_off_sustain_s": 45, "S_min_F": 20, "T_sp_sustain_s": 20, "Max_ramp_s": 900, "Max_stage_s": 7200, "quiet_window_s": 720, "dT_quiet_F_per_min": 2, "allow_main_without_preheat": true, "continue_after_fault_if_next_stage_ramps": true}')
            """)
            
            # Insert default runtime state
            conn.execute("""
                INSERT OR IGNORE INTO fsm_runtime_state (line_id, state, stage, config_version) VALUES 
                ('Line-07', 'IDLE', 'none', 1)
            """)
            
            logger.info("FSM tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create FSM tables: {e}")
            raise
    
    def store_readings(self, device_name: str, timestamp: datetime, readings: Dict[str, float]):
        """Store readings for a device in the new format"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
            
            conn.commit()
            logger.debug(f"Stored readings for {device_name} at {date_str} {time_str}")
            
        except Exception as e:
            logger.error(f"Failed to store readings for {device_name}: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def get_latest_readings(self, device_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get the latest readings for all devices or a specific device using new schema"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
    def get_readings_range(self, device_name: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get readings for a device within a time range using new schema"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
    def get_statistics(self, device_name: str, hours: int = 24) -> Dict[str, Any]:
        """Get statistical data for a device over the specified hours"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
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
        finally:
            if conn:
                conn.close()
    
    def log_event(self, event_type: str, message: str, severity: str = "INFO", device_name: Optional[str] = None):
        """Log a system event"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO events (event_type, device_name, message, severity)
                VALUES (?, ?, ?, ?)
            """, (event_type, device_name, message, severity))
            
            conn.commit()
            logger.debug(f"Logged event: {event_type} - {message}")
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
        finally:
            if conn:
                conn.close()
    
    def get_events(self, limit: int = 100, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent system events"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old data to prevent database bloat"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
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
            
            conn.commit()
            
            logger.info(f"Cleanup completed: {readings_deleted} readings, {events_deleted} events deleted")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def store_setpoint(self, device_name: str, setpoint_value: float, deviation: float = None):
        """Store or update setpoint for a device"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to store setpoint for {device_name}: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def get_setpoint(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest setpoint for a device"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
    def get_all_setpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get all setpoints for all devices"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
    def update_setpoint_deviation(self, device_name: str, deviation: float):
        """Update the deviation for an existing setpoint"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE setpoints 
                SET deviation = ?, timestamp = CURRENT_TIMESTAMP
                WHERE device_name = ?
            """, (deviation, device_name))
            
            if cursor.rowcount > 0:
                conn.commit()
                logger.debug(f"Updated deviation for {device_name}: ±{deviation}°F")
                return True
            else:
                logger.warning(f"No setpoint found for {device_name} to update deviation")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update deviation for {device_name}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_setpoint_history(self, device_name: str, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """
        Get setpoint history for a device during a time period.
        
        Args:
            device_name: Name of the device (e.g., 'preheat', 'main_heat', 'rib_heat')
            start_time: Start time of the period
            end_time: End time of the period
            
        Returns:
            List of dictionaries containing setpoint changes with timestamps
        """
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Convert datetime objects to string format for comparison
            start_datetime_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_datetime_str = end_time.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("""
                SELECT setpoint_value, timestamp
                FROM setpoints
                WHERE device_name = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            """, (device_name, start_datetime_str, end_datetime_str))
            
            setpoint_history = []
            for row in cursor.fetchall():
                setpoint_value, timestamp = row
                setpoint_history.append({
                    'setpoint_value': setpoint_value,
                    'timestamp': timestamp
                })
            
            logger.debug(f"Retrieved {len(setpoint_history)} setpoint changes for {device_name} between {start_time} and {end_time}")
            return setpoint_history
            
        except Exception as e:
            logger.error(f"Failed to get setpoint history for {device_name}: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_database_info(self) -> Dict[str, Any]:
        """Get database statistics and information"""
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
        finally:
            if conn:
                conn.close()
    
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
        conn = None
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
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
            logger.error(f"Failed to get readings for period: {e}")
            return []
            
    # FSM-specific methods
    def get_fsm_config(self, line_id: str) -> Optional[Dict[str, Any]]:
        """Get the latest FSM configuration for a line"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.execute("""
                    SELECT params FROM fsm_config 
                    WHERE line_id = ? 
                    ORDER BY version DESC 
                    LIMIT 1
                """, (line_id,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
                return None
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get FSM config: {e}")
            return None
            
    def update_fsm_config(self, line_id: str, params: Dict[str, Any]) -> bool:
        """Update FSM configuration for a line"""
        try:
            conn = self._get_connection()
            try:
                # Get next version number
                cursor = conn.execute("""
                    SELECT COALESCE(MAX(version), 0) + 1 FROM fsm_config WHERE line_id = ?
                """, (line_id,))
                next_version = cursor.fetchone()[0]
                
                # Insert new config
                conn.execute("""
                    INSERT INTO fsm_config (line_id, version, params) VALUES (?, ?, ?)
                """, (line_id, next_version, json.dumps(params)))
                
                conn.commit()
                logger.info(f"Updated FSM config for {line_id} to version {next_version}")
                return True
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to update FSM config: {e}")
            return False
            
    def get_fsm_runtime_state(self, line_id: str) -> Optional[Dict[str, Any]]:
        """Get current FSM runtime state for a line"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.execute("""
                    SELECT state, run_id, stage, stage_enter_ts, sp_ref, config_version, updated_at
                    FROM fsm_runtime_state WHERE line_id = ?
                """, (line_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'state': row[0],
                        'run_id': row[1],
                        'stage': row[2],
                        'stage_enter_ts': row[3],
                        'sp_ref': row[4],
                        'config_version': row[5],
                        'updated_at': row[6]
                    }
                return None
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get FSM runtime state: {e}")
            return None
            
    def update_fsm_runtime_state(self, line_id: str, state: str, stage: str = 'none', 
                                run_id: str = None, sp_ref: float = None) -> bool:
        """Update FSM runtime state for a line"""
        try:
            conn = self._get_connection()
            try:
                conn.execute("""
                    UPDATE fsm_runtime_state 
                    SET state = ?, stage = ?, run_id = ?, sp_ref = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE line_id = ?
                """, (state, stage, run_id, sp_ref, line_id))
                
                conn.commit()
                return True
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to update FSM runtime state: {e}")
            return False
            
    def create_fsm_run(self, run_id: str, line_id: str, started_at: datetime) -> bool:
        """Create a new FSM run"""
        try:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO fsm_runs (run_id, line_id, started_at, auto)
                    VALUES (?, ?, ?, 1)
                """, (run_id, line_id, started_at.isoformat()))
                
                conn.commit()
                return True
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to create FSM run: {e}")
            return False
            
    def end_fsm_run(self, run_id: str, ended_at: datetime, end_reason: str,
                    preheat_ok: bool = None, main_ok: bool = None, rib_ok: bool = None,
                    preheat_flags: Dict = None, main_flags: Dict = None, rib_flags: Dict = None) -> bool:
        """End an FSM run with results"""
        try:
            conn = self._get_connection()
            try:
                conn.execute("""
                    UPDATE fsm_runs 
                    SET ended_at = ?, end_reason = ?, preheat_ok = ?, main_ok = ?, rib_ok = ?,
                        preheat_flags = ?, main_flags = ?, rib_flags = ?
                    WHERE run_id = ?
                """, (ended_at.isoformat(), end_reason, preheat_ok, main_ok, rib_ok,
                      json.dumps(preheat_flags or {}), json.dumps(main_flags or {}), 
                      json.dumps(rib_flags or {}), run_id))
                
                conn.commit()
                return True
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to end FSM run: {e}")
            return False
            
    def add_fsm_stage(self, run_id: str, stage: str, start_ts: datetime, end_ts: datetime,
                      sp_start: float, sp_end: float, t_min: float, t_max: float,
                      t_mean: float, t_std: float, status: str = 'normal') -> bool:
        """Add a completed stage to an FSM run"""
        try:
            conn = self._get_connection()
            try:
                conn.execute("""
                    INSERT INTO fsm_stages (run_id, stage, start_ts, end_ts, sp_start, sp_end,
                                          t_min, t_max, t_mean, t_std, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (run_id, stage, start_ts.isoformat(), end_ts.isoformat(),
                      sp_start, sp_end, t_min, t_max, t_mean, t_std, status))
                
                conn.commit()
                return True
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to add FSM stage: {e}")
            return False
            
    def get_fsm_runs(self, line_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent FSM runs for a line"""
        try:
            conn = self._get_connection()
            try:
                cursor = conn.execute("""
                    SELECT run_id, started_at, ended_at, end_reason, wo, auto,
                           preheat_ok, main_ok, rib_ok
                    FROM fsm_runs 
                    WHERE line_id = ? 
                    ORDER BY started_at DESC 
                    LIMIT ?
                """, (line_id, limit))
                
                runs = []
                for row in cursor.fetchall():
                    runs.append({
                        'run_id': row[0],
                        'started_at': row[1],
                        'ended_at': row[2],
                        'end_reason': row[3],
                        'wo': row[4],
                        'auto': bool(row[5]),
                        'preheat_ok': row[6],
                        'main_ok': row[7],
                        'rib_ok': row[8]
                    })
                return runs
            finally:
                if conn:
                    conn.close()
        except Exception as e:
            logger.error(f"Failed to get FSM runs: {e}")
            return []
    
    def close(self):
        """Close database connection - not needed with connection pooling"""
        pass 