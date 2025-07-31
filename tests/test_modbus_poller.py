"""
Unit tests for Modbus Poller
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from src.modbus_poller import ModbusPoller, ModbusDevice


class TestModbusDevice:
    """Test ModbusDevice dataclass"""
    
    def test_modbus_device_creation(self):
        """Test creating a ModbusDevice instance"""
        device = ModbusDevice(
            name="Test Sensor",
            ip="192.168.1.100",
            port=502,
            slave_id=1,
            registers={"temperature": 402},
            polling_interval=20
        )
        
        assert device.name == "Test Sensor"
        assert device.ip == "192.168.1.100"
        assert device.port == 502
        assert device.slave_id == 1
        assert device.registers == {"temperature": 402}
        assert device.polling_interval == 20
        assert device.client is None
        assert device.last_reading is None
        assert device.connection_status is False


class TestModbusPoller:
    """Test ModbusPoller class"""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration"""
        return {
            'devices': {
                'sensor_1': {
                    'name': 'Test Sensor 1',
                    'ip': '192.168.1.100',
                    'port': 502,
                    'slave_id': 1,
                    'registers': {
                        'temperature': 402
                    },
                    'polling_interval': 20
                }
            }
        }
    
    @pytest.fixture
    def poller(self, mock_config):
        """Create a ModbusPoller instance with mocked dependencies"""
        with patch('src.modbus_poller.ConfigManager') as mock_config_manager, \
             patch('src.modbus_poller.DatabaseManager') as mock_db_manager:
            
            mock_config_manager.return_value.load_config.return_value = mock_config
            mock_db_manager.return_value.create_tables.return_value = None
            
            poller = ModbusPoller()
            return poller
    
    def test_poller_initialization(self, poller, mock_config):
        """Test ModbusPoller initialization"""
        assert len(poller.devices) == 1
        assert 'sensor_1' in poller.devices
        
        device = poller.devices['sensor_1']
        assert device.name == 'Test Sensor 1'
        assert device.ip == '192.168.1.100'
        assert device.registers == {'temperature': 402, 'pressure': 404}
    
    def test_connect_device_success(self, poller):
        """Test successful device connection"""
        device = poller.devices['sensor_1']
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client.is_socket_open.return_value = False
        
        with patch('src.modbus_poller.ModbusTcpClient', return_value=mock_client):
            result = poller._connect_device(device)
            
            assert result is True
            assert device.connection_status is True
            assert device.client == mock_client
    
    def test_connect_device_failure(self, poller):
        """Test failed device connection"""
        device = poller.devices['sensor_1']
        mock_client = Mock()
        mock_client.connect.return_value = False
        
        with patch('src.modbus_poller.ModbusTcpClient', return_value=mock_client):
            result = poller._connect_device(device)
            
            assert result is False
            assert device.connection_status is False
    
    def test_read_register_success(self, poller):
        """Test successful register reading"""
        device = poller.devices['sensor_1']
        mock_client = Mock()
        mock_client.is_socket_open.return_value = True
        
        mock_result = Mock()
        mock_result.isError.return_value = False
        mock_result.registers = [0x4228, 0x0000]  # Example 32-bit float value
        
        mock_client.read_input_registers.return_value = mock_result
        device.client = mock_client
        device.connection_status = True
        
        with patch('src.modbus_poller.BinaryPayloadDecoder') as mock_decoder:
            mock_decoder_instance = Mock()
            mock_decoder_instance.decode_32bit_float.return_value = 42.5
            mock_decoder.fromRegisters.return_value = mock_decoder_instance
            
            result = poller._read_register(device, 'temperature', 402)
            
            assert result == 42.5
            mock_client.read_input_registers.assert_called_once_with(402, 2, slave=1)
    
    def test_read_register_error(self, poller):
        """Test register reading error"""
        device = poller.devices['sensor_1']
        mock_client = Mock()
        mock_client.is_socket_open.return_value = True
        
        mock_result = Mock()
        mock_result.isError.return_value = True
        
        mock_client.read_input_registers.return_value = mock_result
        device.client = mock_client
        device.connection_status = True
        
        result = poller._read_register(device, 'temperature', 402)
        
        assert result is None
    
    def test_get_status(self, poller):
        """Test getting poller status"""
        device = poller.devices['sensor_1']
        device.last_reading = datetime(2023, 1, 1, 12, 0, 0)
        device.connection_status = True
        
        status = poller.get_status()
        
        assert status['running'] is False
        assert 'sensor_1' in status['devices']
        assert status['devices']['sensor_1']['name'] == 'Test Sensor 1'
        assert status['devices']['sensor_1']['connected'] is True
        assert status['devices']['sensor_1']['last_reading'] == '2023-01-01T12:00:00'
        assert 'temperature' in status['devices']['sensor_1']['registers']


if __name__ == '__main__':
    pytest.main([__file__]) 