"""
Modbus TCP Polling Service

Handles concurrent polling of multiple Modbus TCP devices,
data collection, and storage to both SQLite and CSV formats.
"""

import os
import time
import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
import yaml
import pytz

from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian
from pymodbus.exceptions import ModbusException

from .database import DatabaseManager
from .config_manager import ConfigManager

# Configure logging
# Setup logging with error handling
def setup_logging():
    """Setup logging with proper error handling"""
    try:
        # Ensure logs directory exists
        os.makedirs('logs', exist_ok=True)
        
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/modbus_poller.log'),
                logging.StreamHandler()
            ]
        )
    except Exception as e:
        # Fallback to console-only logging if file logging fails
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler()]
        )
        print(f"Warning: Could not setup file logging: {e}")

setup_logging()
logger = logging.getLogger(__name__)


@dataclass
class ModbusDevice:
    """Represents a Modbus device configuration"""
    name: str
    ip: str
    port: int
    slave_id: int
    registers: Dict[str, int]
    setpoint_register: Optional[int] = None
    polling_interval: int = 20
    client: Optional[ModbusTcpClient] = None
    last_reading: Optional[datetime] = None
    connection_status: bool = False


class ModbusPoller:
    """Main Modbus polling service"""
    
    def __init__(self, config_path: str = "config/"):
        self.config_manager = ConfigManager(config_path)
        self.db_manager = DatabaseManager()
        self.devices: Dict[str, ModbusDevice] = {}
        self.running = False
        self.threads: List[threading.Thread] = []
        
        # Set timezone to CST to match web interface
        self.cst_tz = pytz.timezone('America/Chicago')
        
        self._load_devices()
        self._setup_database()
    
    def _load_devices(self):
        """Load device configurations from YAML file"""
        try:
            config = self.config_manager.load_devices_config()
            devices_config = config.get('devices', {})
            
            for device_id, device_config in devices_config.items():
                device = ModbusDevice(
                    name=device_config['name'],
                    ip=device_config['ip'],
                    port=device_config['port'],
                    slave_id=device_config['slave_id'],
                    registers=device_config['registers'],
                    setpoint_register=device_config['registers'].get('setpoint_register'),
                    polling_interval=device_config.get('polling_interval', 20)
                )
                self.devices[device_id] = device
                logger.info(f"Loaded device: {device.name} at {device.ip}")
                logger.info(f"Device {device.name} setpoint_register: {device.setpoint_register}")
                
        except Exception as e:
            logger.error(f"Failed to load device configuration: {e}")
            raise
    
    def _setup_database(self):
        """Initialize database tables"""
        try:
            self.db_manager.create_tables()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Failed to setup database: {e}")
            raise
    
    def _connect_device(self, device: ModbusDevice) -> bool:
        """Connect to a Modbus device"""
        try:
            if device.client and device.client.is_socket_open():
                return True
                
            device.client = ModbusTcpClient(device.ip, port=device.port)
            if device.client.connect():
                device.connection_status = True
                logger.info(f"Connected to {device.name} at {device.ip}")
                return True
            else:
                device.connection_status = False
                logger.error(f"Failed to connect to {device.name} at {device.ip}")
                return False
                
        except Exception as e:
            device.connection_status = False
            logger.error(f"Connection error for {device.name}: {e}")
            return False
    
    def _read_register(self, device: ModbusDevice, register_name: str, register_address: int) -> Optional[float]:
        """Read a single register from a device - using exact same method as working script"""
        logger.info(f"=== ENTERING _read_register for {device.name} register {register_name} ===")
        # Check connection first
        if not device.client or not device.client.is_socket_open():
            if not self._connect_device(device):
                return None
        
        # Use exact same method as the working single sensor script - NO exception handling around decoder
        result = device.client.read_input_registers(register_address, 2, slave=1)
        if not result.isError():
            logger.debug(f"Raw registers from {device.name}: {result.registers}")
            try:
                decoder = BinaryPayloadDecoder.fromRegisters(
                    result.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE
                )
                logger.debug(f"Created decoder for {device.name}")
                
                temp = decoder.decode_32bit_float()
                logger.debug(f"Decoded temperature from {device.name}: {temp} (type: {type(temp)})")
                
                # Ensure we return a float value
                if temp is not None:
                    try:
                        float_temp = float(temp)
                        # Round to whole number
                        rounded_temp = round(float_temp)
                        logger.debug(f"Converted temperature to float: {float_temp}, rounded to: {rounded_temp}")
                        logger.info(f"=== EXITING _read_register for {device.name} with value {rounded_temp} ===")
                        return rounded_temp
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to convert temperature to float: {temp}, error: {e}")
                        return None
                else:
                    logger.warning(f"Decoded temperature is None for {device.name}")
                    return None
            except Exception as e:
                logger.error(f"Error in decoding for {device.name}: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                return None
        else:
            logger.warning(f"Error reading register {register_name} from {device.name}")
            return None
    
    def _read_setpoint_register(self, device: ModbusDevice, register_address: int) -> Optional[float]:
        """Read setpoint register with correct decoding for setpoint values"""
        logger.info(f"=== ENTERING _read_setpoint_register for {device.name} ===")
        # Check connection first
        if not device.client or not device.client.is_socket_open():
            if not self._connect_device(device):
                return None
        
        # Read setpoint register
        result = device.client.read_input_registers(register_address, 2, slave=1)
        if not result.isError():
            logger.debug(f"Raw setpoint registers from {device.name}: {result.registers}")
            try:
                # Use same word order as temperature readings
                decoder = BinaryPayloadDecoder.fromRegisters(
                    result.registers,
                    byteorder=Endian.BIG,
                    wordorder=Endian.LITTLE
                )
                logger.debug(f"Created setpoint decoder for {device.name}")
                
                setpoint = decoder.decode_32bit_float()
                logger.debug(f"Decoded setpoint from {device.name}: {setpoint} (type: {type(setpoint)})")
                
                # Ensure we return a float value
                if setpoint is not None:
                    try:
                        float_setpoint = float(setpoint)
                        # Round to whole number
                        rounded_setpoint = round(float_setpoint)
                        logger.debug(f"Converted setpoint to float: {float_setpoint}, rounded to: {rounded_setpoint}")
                        logger.info(f"=== EXITING _read_setpoint_register for {device.name} with value {rounded_setpoint} ===")
                        return rounded_setpoint
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to convert setpoint to float: {setpoint}, error: {e}")
                        return None
                else:
                    logger.warning(f"Decoded setpoint is None for {device.name}")
                    return None
            except Exception as e:
                logger.error(f"Error in setpoint decoding for {device.name}: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                return None
        else:
            logger.warning(f"Error reading setpoint register from {device.name}")
            return None
    
    def _poll_device(self, device: ModbusDevice):
        """Poll a single device continuously"""
        logger.info(f"Starting polling for {device.name}")
        
        while self.running:
            try:
                timestamp = datetime.now(self.cst_tz)
                readings = {}
                
                # Read all registers for this device
                for register_name, register_address in device.registers.items():
                    value = self._read_register(device, register_name, register_address)
                    if value is not None:
                        readings[register_name] = value
                
                # Store readings if we got any valid data
                if readings:
                    device.last_reading = timestamp
                    
                    # Store in database (device_name is used to identify which column to update)
                    self.db_manager.store_readings(device.name, timestamp, readings)
                    
                    # Log to CSV
                    self._log_to_csv(device.name, timestamp, readings)
                    
                    logger.debug(f"{device.name}: {readings}")
                else:
                    logger.warning(f"No valid readings from {device.name}")
                
                # Read setpoint using correct decoding for setpoint registers
                if device.setpoint_register:
                    logger.info(f"Reading setpoint for {device.name} at address {device.setpoint_register}")
                    setpoint_value = self._read_setpoint_register(device, device.setpoint_register)
                    if setpoint_value is not None:
                        logger.info(f"Successfully read setpoint for {device.name}: {setpoint_value}°F")
                        # Store setpoint in database with default deviation of 5.0°F
                        self.db_manager.store_setpoint(device.name, setpoint_value, 5.0)
                    else:
                        logger.warning(f"Failed to read setpoint for {device.name}")
                else:
                    logger.debug(f"No setpoint register configured for {device.name}")
                
                # Wait for next polling interval
                time.sleep(device.polling_interval)
                
            except Exception as e:
                logger.error(f"Error in polling loop for {device.name}: {e}")
                logger.error(f"Exception type: {type(e).__name__}")
                logger.error(f"Exception details: {str(e)}")
                time.sleep(device.polling_interval)
    

    
    def _log_to_csv(self, device_name: str, timestamp: datetime, readings: Dict[str, float]):
        """Log readings to CSV file"""
        try:
            # Replace spaces with underscores for filename safety
            safe_device_name = device_name.replace(' ', '_')
            csv_filename = f"logs/{safe_device_name}_{timestamp.strftime('%Y%m%d')}.csv"
            
            # Create CSV file with headers if it doesn't exist
            import os
            import csv
            
            file_exists = os.path.exists(csv_filename)
            
            with open(csv_filename, 'a', newline='') as csvfile:
                writer = csv.writer(csvfile)
                
                if not file_exists:
                    # Write headers with units
                    headers = ['Timestamp'] + [f"{key} (°F)" for key in readings.keys()]
                    writer.writerow(headers)
                
                # Write data row
                row = [timestamp.strftime('%Y-%m-%d %H:%M:%S')] + list(readings.values())
                writer.writerow(row)
                
        except Exception as e:
            logger.error(f"Failed to log to CSV for {device_name}: {e}")
    
    def start(self):
        """Start polling all devices"""
        if self.running:
            logger.warning("Poller is already running")
            return
        
        self.running = True
        logger.info("Starting Modbus poller service")
        
        # Start a thread for each device
        for device_id, device in self.devices.items():
            thread = threading.Thread(
                target=self._poll_device,
                args=(device,),
                name=f"poller-{device_id}",
                daemon=True
            )
            thread.start()
            self.threads.append(thread)
            logger.info(f"Started polling thread for {device.name}")
    
    def stop(self):
        """Stop polling all devices"""
        if not self.running:
            return
        
        logger.info("Stopping Modbus poller service")
        self.running = False
        
        # Wait for threads to finish
        for thread in self.threads:
            thread.join(timeout=5)
        
        # Close all device connections
        for device in self.devices.values():
            if device.client and device.client.is_socket_open():
                device.client.close()
                logger.info(f"Closed connection to {device.name}")
        
        logger.info("Modbus poller service stopped")
    
    def get_status(self) -> Dict:
        """Get status of all devices"""
        status = {
            'running': self.running,
            'devices': {}
        }
        
        for device_id, device in self.devices.items():
            status['devices'][device_id] = {
                'name': device.name,
                'ip': device.ip,
                'connected': device.connection_status,
                'last_reading': device.last_reading.isoformat() if device.last_reading else None,
                'registers': list(device.registers.keys())
            }
        
        return status


def main():
    """Main entry point for the Modbus poller service"""
    try:
        poller = ModbusPoller()
        poller.start()
        
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            poller.stop()
            
    except Exception as e:
        logger.error(f"Fatal error in Modbus poller: {e}")
        raise


if __name__ == "__main__":
    main() 