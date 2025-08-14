#!/usr/bin/env python3
"""
Debug script for report generation

This script will test each component of the report generation
to identify where the issue is occurring.
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_imports():
    """Test if all required modules can be imported"""
    print("Testing imports...")
    try:
        from src.database import DatabaseManager
        print("✓ DatabaseManager imported successfully")
    except Exception as e:
        print(f"✗ Failed to import DatabaseManager: {e}")
        return False
    
    try:
        from src.config_manager import ConfigManager
        print("✓ ConfigManager imported successfully")
    except Exception as e:
        print(f"✗ Failed to import ConfigManager: {e}")
        return False
    
    try:
        from src.report_generator import ReportGenerator
        print("✓ ReportGenerator imported successfully")
    except Exception as e:
        print(f"✗ Failed to import ReportGenerator: {e}")
        return False
    
    return True

def test_directories():
    """Test if required directories exist and are writable"""
    print("\nTesting directories...")
    
    # Check reports directory
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        print(f"Creating reports directory: {reports_dir}")
        os.makedirs(reports_dir, exist_ok=True)
    
    if os.path.exists(reports_dir):
        print(f"✓ Reports directory exists: {reports_dir}")
        if os.access(reports_dir, os.W_OK):
            print(f"✓ Reports directory is writable")
        else:
            print(f"✗ Reports directory is not writable")
            return False
    else:
        print(f"✗ Failed to create reports directory")
        return False
    
    # Check data directory
    data_dir = "data"
    if not os.path.exists(data_dir):
        print(f"Creating data directory: {data_dir}")
        os.makedirs(data_dir, exist_ok=True)
    
    if os.path.exists(data_dir):
        print(f"✓ Data directory exists: {data_dir}")
    else:
        print(f"✗ Failed to create data directory")
        return False
    
    return True

def test_database():
    """Test database operations"""
    print("\nTesting database...")
    try:
        from src.database import DatabaseManager
        db_manager = DatabaseManager()
        db_manager.create_tables()
        print("✓ Database tables created successfully")
        
        # Test storing some sample data
        test_time = datetime.now()
        db_manager.store_readings("preheat", test_time, {"temperature": 250.0})
        db_manager.store_readings("main_heat", test_time, {"temperature": 350.0})
        db_manager.store_readings("rib_heat", test_time, {"temperature": 300.0})
        print("✓ Sample data stored successfully")
        
        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def test_report_generation():
    """Test report generation"""
    print("\nTesting report generation...")
    try:
        from src.database import DatabaseManager
        from src.config_manager import ConfigManager
        from src.report_generator import ReportGenerator
        
        # Initialize components
        config_manager = ConfigManager()
        db_manager = DatabaseManager()
        report_generator = ReportGenerator(db_manager, config_manager)
        
        # Generate sample data for the last hour
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        
        # Test PDF report generation
        print("Generating PDF report...")
        pdf_report = report_generator.generate_work_order_report(
            work_order_number="WO-DEBUG-001",
            start_time=start_time,
            end_time=end_time,
            machine_id="Line-07",
            output_format="pdf"
        )
        
        print(f"✓ PDF report generated: {pdf_report['file_path']}")
        print(f"✓ Report ID: {pdf_report['report_id']}")
        
        # Check if file actually exists
        if os.path.exists(pdf_report['file_path']):
            print(f"✓ Report file exists on disk")
            file_size = os.path.getsize(pdf_report['file_path'])
            print(f"✓ Report file size: {file_size} bytes")
        else:
            print(f"✗ Report file does not exist on disk")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Report generation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("=== Vulcan Sentinel Report Generation Debug ===\n")
    
    tests = [
        ("Imports", test_imports),
        ("Directories", test_directories),
        ("Database", test_database),
        ("Report Generation", test_report_generation),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running {test_name} Test")
        print(f"{'='*50}")
        
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"✗ {test_name} test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print(f"{'='*50}")
    
    all_passed = True
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print(f"\n🎉 All tests passed! Report generation should work.")
    else:
        print(f"\n❌ Some tests failed. Check the output above for details.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
