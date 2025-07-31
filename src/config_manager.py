"""
Configuration Manager

Handles loading and validation of configuration files
for the industrial data logging system.
"""

import yaml
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages application configuration"""
    
    def __init__(self, config_path: str = "config/"):
        self.config_path = Path(config_path)
        self._config_cache = {}
    
    def load_config(self, config_file: str = "app_config.yaml") -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            config_file_path = self.config_path / config_file
            
            if not config_file_path.exists():
                logger.warning(f"Config file not found: {config_file_path}")
                return self._get_default_config()
            
            with open(config_file_path, 'r', encoding='utf-8') as file:
                config = yaml.safe_load(file)
            
            # Cache the configuration
            self._config_cache[config_file] = config
            
            logger.info(f"Loaded configuration from {config_file_path}")
            return config
            
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML config file {config_file}: {e}")
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Error loading config file {config_file}: {e}")
            return self._get_default_config()
    
    def load_devices_config(self) -> Dict[str, Any]:
        """Load devices configuration"""
        return self.load_config("devices.yaml")
    
    def load_printer_config(self) -> Dict[str, Any]:
        """Load printer configuration"""
        return self.load_config("printer_config.yaml")
    
    def save_config(self, config: Dict[str, Any], config_file: str = "app_config.yaml"):
        """Save configuration to YAML file"""
        try:
            config_file_path = self.config_path / config_file
            
            # Ensure config directory exists
            self.config_path.mkdir(parents=True, exist_ok=True)
            
            with open(config_file_path, 'w', encoding='utf-8') as file:
                yaml.dump(config, file, default_flow_style=False, indent=2)
            
            # Update cache
            self._config_cache[config_file] = config
            
            logger.info(f"Saved configuration to {config_file_path}")
            
        except Exception as e:
            logger.error(f"Error saving config file {config_file}: {e}")
            raise
    
    def get_config(self, config_file: str = "app_config.yaml") -> Dict[str, Any]:
        """Get configuration from cache or load from file"""
        if config_file not in self._config_cache:
            return self.load_config(config_file)
        return self._config_cache[config_file]
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration structure"""
        try:
            # Basic validation - add more specific validation as needed
            required_keys = ['app_name', 'version']
            
            for key in required_keys:
                if key not in config:
                    logger.error(f"Missing required config key: {key}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating configuration: {e}")
            return False
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'app_name': 'Industrial Data Logger',
            'version': '1.0.0',
            'log_level': 'INFO',
            'database': {
                'path': 'data/datalogger.db',
                'backup_interval_hours': 24
            },
            'api': {
                'host': '0.0.0.0',
                'port': 8080,
                'debug': False
            },
            'polling': {
                'default_interval': 20,
                'retry_attempts': 3,
                'retry_delay': 5
            }
        }
    
    def create_default_configs(self):
        """Create default configuration files if they don't exist"""
        try:
            # Create config directory
            self.config_path.mkdir(parents=True, exist_ok=True)
            
            # Default app config
            app_config = self._get_default_config()
            self.save_config(app_config, "app_config.yaml")
            
            # Default devices config
            devices_config = {
                'devices': {
                    'sensor_1': {
                        'name': 'Temperature Sensor 1',
                        'ip': '169.254.1.1',
                        'port': 502,
                        'slave_id': 1,
                        'registers': {
                            'temperature': 402
                        },
                        'polling_interval': 20
                    },
                    'sensor_2': {
                        'name': 'Temperature Sensor 2',
                        'ip': '169.254.1.2',
                        'port': 502,
                        'slave_id': 1,
                        'registers': {
                            'temperature': 402
                        },
                        'polling_interval': 20
                    },
                    'sensor_3': {
                        'name': 'Temperature Sensor 3',
                        'ip': '169.254.1.3',
                        'port': 502,
                        'slave_id': 1,
                        'registers': {
                            'temperature': 402
                        },
                        'polling_interval': 20
                    }
                }
            }
            self.save_config(devices_config, "devices.yaml")
            
            # Default printer config
            printer_config = {
                'printer': {
                    'name': 'USB_Thermal_Printer',
                    'connection': 'usb://0x0483/0x5740',
                    'paper_width': 80,
                    'print_quality': 'high',
                    'auto_cut': True,
                    'font_size': 'normal',
                    'alignment': 'left'
                },
                'receipt_template': {
                    'company_name': 'Industrial Data Logger',
                    'header_lines': [
                        'JOB SUMMARY REPORT',
                        'Generated: {timestamp}'
                    ],
                    'footer_lines': [
                        'Thank you for using our system',
                        'Report ID: {report_id}'
                    ]
                }
            }
            self.save_config(printer_config, "printer_config.yaml")
            
            logger.info("Created default configuration files")
            
        except Exception as e:
            logger.error(f"Error creating default configs: {e}")
            raise
    
    def reload_config(self, config_file: str = "app_config.yaml"):
        """Reload configuration from file"""
        try:
            if config_file in self._config_cache:
                del self._config_cache[config_file]
            
            return self.load_config(config_file)
            
        except Exception as e:
            logger.error(f"Error reloading config {config_file}: {e}")
            raise
    
    def get_config_value(self, key_path: str, default: Any = None, config_file: str = "app_config.yaml") -> Any:
        """Get a specific configuration value using dot notation"""
        try:
            config = self.get_config(config_file)
            
            # Split the key path by dots
            keys = key_path.split('.')
            value = config
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return default
            
            return value
            
        except Exception as e:
            logger.error(f"Error getting config value {key_path}: {e}")
            return default
    
    def set_config_value(self, key_path: str, value: Any, config_file: str = "app_config.yaml"):
        """Set a specific configuration value using dot notation"""
        try:
            config = self.get_config(config_file)
            
            # Split the key path by dots
            keys = key_path.split('.')
            current = config
            
            # Navigate to the parent of the target key
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            
            # Set the value
            current[keys[-1]] = value
            
            # Save the updated configuration
            self.save_config(config, config_file)
            
            logger.info(f"Set config value {key_path} = {value}")
            
        except Exception as e:
            logger.error(f"Error setting config value {key_path}: {e}")
            raise 