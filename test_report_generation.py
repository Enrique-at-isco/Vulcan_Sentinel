#!/usr/bin/env python3
"""
Test script for report generation functionality

This script demonstrates how to generate work order reports
using the Vulcan Sentinel report generator.
"""

import os
import sys
import logging
from datetime import datetime, timedelta
import random

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.database import DatabaseManager
from src.config_manager import ConfigManager
from src.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_sample_data(db_manager, start_time, end_time):
    """Generate sample temperature data for testing"""
    logger.info("Generating sample temperature data...")
    
    # Sample data for the three sensors
    sensors = ['preheat', 'main_heat', 'rib_heat']
    
    current_time = start_time
    while current_time <= end_time:
        for sensor in sensors:
            # Generate realistic temperature values
            if sensor == 'preheat':
                base_temp = 250 + random.uniform(-20, 30)
            elif sensor == 'main_heat':
                base_temp = 350 + random.uniform(-30, 40)
            else:  # rib_heat
                base_temp = 300 + random.uniform(-25, 35)
            
            # Add some noise
            temp = base_temp + random.uniform(-5, 5)
            
            # Store the reading
            db_manager.store_readings(sensor, current_time, {'temperature': temp})
        
        # Log some events
        if current_time.minute % 5 == 0:  # Every 5 minutes
            db_manager.log_event(
                event_type="TEMP_REACHED",
                message=f"Temperature target reached for {sensors[0]}",
                severity="INFO",
                device_name=sensors[0]
            )
        
        if current_time.minute % 10 == 0:  # Every 10 minutes
            db_manager.log_event(
                event_type="MANUAL_OVERRIDE",
                message="Set temperature manually adjusted",
                severity="WARNING",
                device_name=sensors[1]
            )
        
        current_time += timedelta(seconds=20)  # 20-second intervals
    
    logger.info("Sample data generation completed")


def test_report_generation():
    """Test the report generation functionality"""
    try:
        logger.info("Starting report generation test...")
        
        # Initialize components
        config_manager = ConfigManager()
        db_manager = DatabaseManager()
        report_generator = ReportGenerator(db_manager, config_manager)
        
        # Create database tables
        db_manager.create_tables()
        
        # Generate sample data for the last hour
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        
        generate_sample_data(db_manager, start_time, end_time)
        
        # Test PDF report generation
        logger.info("Generating PDF report...")
        pdf_report = report_generator.generate_work_order_report(
            work_order_number="WO-TEST-001",
            start_time=start_time,
            end_time=end_time,
            machine_id="Line-07",
            output_format="pdf"
        )
        
        logger.info(f"PDF report generated: {pdf_report['file_path']}")
        logger.info(f"Report ID: {pdf_report['report_id']}")
        
        # Test thermal report generation
        logger.info("Generating thermal report...")
        thermal_report = report_generator.generate_work_order_report(
            work_order_number="WO-TEST-002",
            start_time=start_time,
            end_time=end_time,
            machine_id="Line-07",
            output_format="thermal"
        )
        
        logger.info(f"Thermal report generated: {thermal_report['file_path']}")
        logger.info(f"Report ID: {thermal_report['report_id']}")
        
        # Test report history
        logger.info("Getting report history...")
        history = report_generator.get_report_history(10)
        logger.info(f"Found {len(history)} reports in history")
        
        for report in history:
            logger.info(f"  - Report {report['report_id']}: {report['work_order_number']}")
        
        # Test CSV export
        if history:
            logger.info("Testing CSV export...")
            csv_path = report_generator.export_report_csv(history[0]['report_id'])
            logger.info(f"CSV exported to: {csv_path}")
        
        logger.info("Report generation test completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False


if __name__ == "__main__":
    success = test_report_generation()
    sys.exit(0 if success else 1)
