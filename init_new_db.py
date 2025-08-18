#!/usr/bin/env python3
"""
Initialize new database schema for Vulcan Sentinel
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.database import DatabaseManager
from src.config_manager import ConfigManager
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_new_database():
    """Initialize the new database schema"""
    
    try:
        # Remove old database if it exists
        db_path = "data/vulcan_sentinel.db"
        if os.path.exists(db_path):
            logger.info(f"Removing old database: {db_path}")
            os.remove(db_path)
        
        # Initialize new database
        logger.info("Initializing new database schema...")
        db_manager = DatabaseManager(db_path)
        db_manager.create_tables()
        
        # Load device configurations
        config_manager = ConfigManager("config/")
        devices_config = config_manager.load_devices_config()
        
        # Insert device configurations into devices table
        logger.info("Inserting device configurations...")
        for device_id, device_config in devices_config.get('devices', {}).items():
            try:
                db_manager.conn.cursor().execute("""
                    INSERT INTO devices (name, ip_address, port, slave_id, register_address)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    device_config['name'],
                    device_config['ip'],
                    device_config['port'],
                    device_config['slave_id'],
                    device_config['registers']['temperature']  # Assuming temperature register
                ))
                logger.info(f"Added device: {device_config['name']}")
            except Exception as e:
                logger.error(f"Error adding device {device_config['name']}: {e}")
        
        db_manager.conn.commit()
        logger.info("Database initialization completed successfully!")
        
        # Show database structure
        cursor = db_manager.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        logger.info(f"Created tables: {[table[0] for table in tables]}")
        
        # Show device configurations
        cursor.execute("SELECT name, ip_address, port, slave_id FROM devices")
        devices = cursor.fetchall()
        logger.info(f"Configured devices: {[device[0] for device in devices]}")
        
        db_manager.conn.close()
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

if __name__ == "__main__":
    init_new_database()
