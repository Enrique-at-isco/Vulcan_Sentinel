#!/usr/bin/env python3
"""
Performance Monitor for Vulcan Sentinel

Monitors system performance metrics including:
- CPU and memory usage
- Database size and query performance
- Log file sizes
- Network connectivity
- Disk usage
"""

import os
import time
import psutil
import sqlite3
import logging
from datetime import datetime, timedelta
import json
import pytz

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class PerformanceMonitor:
    """Monitor system performance metrics"""
    
    def __init__(self, db_path="data/vulcan_sentinel.db"):
        self.db_path = db_path
        self.cst_tz = pytz.timezone('America/Chicago')
        
    def get_system_metrics(self):
        """Get system performance metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            
            # Disk usage
            disk = psutil.disk_usage('/')
            
            # Network I/O
            network = psutil.net_io_counters()
            
            return {
                'timestamp': datetime.now(self.cst_tz).isoformat(),
                'cpu_percent': cpu_percent,
                'memory': {
                    'total_gb': round(memory.total / (1024**3), 2),
                    'used_gb': round(memory.used / (1024**3), 2),
                    'available_gb': round(memory.available / (1024**3), 2),
                    'percent': memory.percent
                },
                'disk': {
                    'total_gb': round(disk.total / (1024**3), 2),
                    'used_gb': round(disk.used / (1024**3), 2),
                    'free_gb': round(disk.free / (1024**3), 2),
                    'percent': round((disk.used / disk.total) * 100, 2)
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'packets_sent': network.packets_sent,
                    'packets_recv': network.packets_recv
                }
            }
        except Exception as e:
            logger.error(f"Error getting system metrics: {e}")
            return {}
    
    def get_database_metrics(self):
        """Get database performance metrics"""
        try:
            if not os.path.exists(self.db_path):
                return {'error': 'Database file not found'}
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Database file size
            db_size_bytes = os.path.getsize(self.db_path)
            db_size_mb = round(db_size_bytes / (1024**2), 2)
            
            # Record counts
            cursor.execute("SELECT COUNT(*) FROM readings")
            total_records = cursor.fetchone()[0]
            
            # Recent records (last 24 hours)
            yesterday = (datetime.now(self.cst_tz) - timedelta(days=1)).strftime('%Y-%m-%d')
            cursor.execute("SELECT COUNT(*) FROM readings WHERE date >= ?", (yesterday,))
            recent_records = cursor.fetchone()[0]
            
            # Oldest and newest records
            cursor.execute("SELECT MIN(date), MAX(date) FROM readings")
            date_range = cursor.fetchone()
            oldest_date = date_range[0] if date_range[0] else 'N/A'
            newest_date = date_range[1] if date_range[1] else 'N/A'
            
            # Query performance test
            start_time = time.time()
            cursor.execute("SELECT * FROM readings ORDER BY date DESC, timestamp DESC LIMIT 100")
            cursor.fetchall()
            query_time_ms = round((time.time() - start_time) * 1000, 2)
            
            conn.close()
            
            return {
                'db_size_mb': db_size_mb,
                'total_records': total_records,
                'recent_records_24h': recent_records,
                'oldest_date': oldest_date,
                'newest_date': newest_date,
                'query_performance_ms': query_time_ms
            }
            
        except Exception as e:
            logger.error(f"Error getting database metrics: {e}")
            return {'error': str(e)}
    
    def get_log_metrics(self):
        """Get log file metrics"""
        try:
            log_dir = "logs"
            if not os.path.exists(log_dir):
                return {'error': 'Logs directory not found'}
            
            log_files = {}
            total_size_mb = 0
            
            for filename in os.listdir(log_dir):
                if filename.endswith('.log') or filename.endswith('.csv'):
                    filepath = os.path.join(log_dir, filename)
                    file_size_bytes = os.path.getsize(filepath)
                    file_size_mb = round(file_size_bytes / (1024**2), 2)
                    
                    log_files[filename] = {
                        'size_mb': file_size_mb,
                        'modified': datetime.fromtimestamp(os.path.getmtime(filepath), self.cst_tz).isoformat()
                    }
                    total_size_mb += file_size_mb
            
            return {
                'total_log_size_mb': round(total_size_mb, 2),
                'files': log_files
            }
            
        except Exception as e:
            logger.error(f"Error getting log metrics: {e}")
            return {'error': str(e)}
    
    def get_performance_report(self):
        """Generate comprehensive performance report"""
        try:
            system_metrics = self.get_system_metrics()
            db_metrics = self.get_database_metrics()
            log_metrics = self.get_log_metrics()
            
            report = {
                'timestamp': datetime.now(self.cst_tz).isoformat(),
                'system': system_metrics,
                'database': db_metrics,
                'logs': log_metrics
            }
            
            # Add performance warnings
            warnings = []
            
            if system_metrics.get('memory', {}).get('percent', 0) > 80:
                warnings.append("High memory usage detected")
            
            if system_metrics.get('disk', {}).get('percent', 0) > 85:
                warnings.append("High disk usage detected")
            
            if log_metrics.get('total_log_size_mb', 0) > 100:
                warnings.append("Large log files detected")
            
            if db_metrics.get('query_performance_ms', 0) > 100:
                warnings.append("Slow database queries detected")
            
            report['warnings'] = warnings
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {'error': str(e)}
    
    def save_performance_report(self, report, filename=None):
        """Save performance report to file"""
        try:
            if filename is None:
                timestamp = datetime.now(self.cst_tz).strftime('%Y%m%d_%H%M%S')
                filename = f"logs/performance_report_{timestamp}.json"
            
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"Performance report saved to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving performance report: {e}")

def main():
    """Main function for performance monitoring"""
    monitor = PerformanceMonitor()
    
    print("=== Vulcan Sentinel Performance Monitor ===")
    print(f"Timestamp: {datetime.now(monitor.cst_tz).strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Generate and display report
    report = monitor.get_performance_report()
    
    if 'error' in report:
        print(f"Error: {report['error']}")
        return
    
    # Display system metrics
    print("System Metrics:")
    print(f"  CPU Usage: {report['system'].get('cpu_percent', 'N/A')}%")
    print(f"  Memory Usage: {report['system'].get('memory', {}).get('percent', 'N/A')}%")
    print(f"  Disk Usage: {report['system'].get('disk', {}).get('percent', 'N/A')}%")
    print()
    
    # Display database metrics
    print("Database Metrics:")
    print(f"  Database Size: {report['database'].get('db_size_mb', 'N/A')} MB")
    print(f"  Total Records: {report['database'].get('total_records', 'N/A'):,}")
    print(f"  Recent Records (24h): {report['database'].get('recent_records_24h', 'N/A'):,}")
    print(f"  Query Performance: {report['database'].get('query_performance_ms', 'N/A')} ms")
    print()
    
    # Display log metrics
    print("Log Metrics:")
    print(f"  Total Log Size: {report['logs'].get('total_log_size_mb', 'N/A')} MB")
    print()
    
    # Display warnings
    if report.get('warnings'):
        print("Warnings:")
        for warning in report['warnings']:
            print(f"  ⚠️  {warning}")
        print()
    
    # Save report
    monitor.save_performance_report(report)
    
    print("Performance monitoring complete.")

if __name__ == "__main__":
    main()
