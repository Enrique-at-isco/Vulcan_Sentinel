#!/usr/bin/env python3
"""
Test script using exact same method as working single sensor script
"""

import time
import sys
from datetime import datetime
from pymodbus.client import ModbusTcpClient
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.constants import Endian

def test_sensor(ip, name):
    print(f"Testing {name} at {ip}")
    client = ModbusTcpClient(ip, port=502)

    if not client.connect():
        print(f"Failed to connect to {name}.")
        return False

    try:
        for i in range(5):  # Test 5 readings
            result = client.read_input_registers(402, 2, slave=1)
            if not result.isError():
                decoder = BinaryPayloadDecoder.fromRegisters(
                    result.registers,
                    byteorder=Endian.Big,
                    wordorder=Endian.Little
                )
                temp = decoder.decode_32bit_float()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] {name}: {temp} °F")
            else:
                print(f"Error reading temperature from {name}")

            time.sleep(2)

    except Exception as e:
        print(f"Exception reading {name}: {e}")
        print(f"Exception type: {type(e).__name__}")
        return False

    finally:
        client.close()
    
    return True

if __name__ == "__main__":
    print("Testing sensors with exact same method as working script...")
    
    # Test preheat sensor
    test_sensor("169.254.100.100", "preheat")
    print()
    
    # Test main_heat sensor  
    test_sensor("169.254.100.200", "main_heat")
    print()
    
    print("Test completed.") 