"""
Web server for Vulcan Sentinel

Provides a web interface for viewing:
- Real-time temperature data
- Historical data
- System status
- CSV downloads
- Report generation
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, send_file, request
from flask_cors import CORS
import sqlite3
import csv
from io import StringIO, BytesIO
import pytz
import shutil
import psutil

logger = logging.getLogger(__name__)

class VulcanSentinelWebServer:
    """Flask web server for Vulcan Sentinel"""
    
    def __init__(self, db_path="data/vulcan_sentinel.db", host="0.0.0.0", port=8080, 
                 db_manager=None, config_manager=None, report_generator=None):
        self.db_path = db_path
        self.host = host
        self.port = port
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.report_generator = report_generator
        
        # Initialize Flask app with template folder
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        static_dir = os.path.join(os.path.dirname(__file__), 'static')
        self.app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
        CORS(self.app)
        
        # Set timezone to CST
        self.cst_tz = pytz.timezone('America/Chicago')
        
        # Register routes
        self._register_routes()
    
    def _register_routes(self):
        """Register all web routes"""
        
        @self.app.route('/')
        def index():
            """Main dashboard page"""
            return self._get_dashboard()
        
        @self.app.route('/reports')
        def reports():
            """Report generation page"""
            return render_template('reports.html')
        
        @self.app.route('/api/status')
        def api_status():
            """Get system status"""
            return jsonify(self._get_system_status())
        
        @self.app.route('/api/readings')
        def api_readings():
            """Get latest readings"""
            return jsonify(self._get_latest_readings())
        
        @self.app.route('/api/readings/history')
        def api_history():
            """Get historical data"""
            days = request.args.get('days', 1, type=int)
            return jsonify(self._get_historical_data(days))
        
        @self.app.route('/api/devices')
        def api_devices():
            """Get device information"""
            return jsonify(self._get_device_info())
        
        @self.app.route('/api/csv/<device_name>')
        def api_csv(device_name):
            """Download CSV data for a device"""
            return self._get_csv_data(device_name)
        
        @self.app.route('/health')
        def health():
            """Health check endpoint"""
            return jsonify({"status": "healthy", "timestamp": datetime.now(self.cst_tz).isoformat()})
        
        @self.app.route('/api/cleanup-duplicates')
        def api_cleanup_duplicates():
            """Clean up duplicate readings with same timestamp"""
            return jsonify(self._cleanup_duplicate_readings())
        
        @self.app.route('/api/storage-info')
        def api_storage_info():
            """Get storage usage information"""
            return jsonify(self._get_storage_info())
        
        # Report generation endpoints
        @self.app.route('/api/reports/generate', methods=['POST'])
        def api_generate_report():
            """Generate a work order report"""
            return jsonify(self._generate_report())
        
        @self.app.route('/api/reports/history')
        def api_report_history():
            """Get report history"""
            limit = request.args.get('limit', 50, type=int)
            return jsonify(self._get_report_history(limit))
        
        @self.app.route('/api/reports/download/<report_id>')
        def api_download_report(report_id):
            """Download a specific report"""
            return self._download_report(report_id)
        
        @self.app.route('/api/reports/csv/<report_id>')
        def api_export_csv(report_id):
            """Export report data to CSV"""
            return self._export_report_csv(report_id)
    
    def _get_dashboard(self):
        """Generate dashboard HTML using Flask templates"""
        try:
            # Get latest data
            readings = self._get_latest_readings()
            status = self._get_system_status()
            
            # Ensure readings is a dictionary
            if not isinstance(readings, dict):
                readings = {}
            
            # Ensure status has devices
            if not isinstance(status, dict) or 'devices' not in status:
                status = {'devices': {}}
            
            # Render template with data
            return render_template('dashboard.html', 
                                 readings=readings, 
                                 status=status,
                                 current_time=datetime.now(self.cst_tz).strftime('%Y-%m-%d %H:%M:%S'),
                                 format_timestamp_cst=self._format_timestamp_cst)
            
        except Exception as e:
            logger.error(f"Error generating dashboard: {e}")
            return f"<h1>Error</h1><p>{str(e)}</p>"
    
    def _format_timestamp_cst(self, timestamp_str):
        """Format timestamp to CST timezone with military time"""
        try:
            if timestamp_str == 'N/A':
                return 'N/A'
            
            # Parse the timestamp (assuming it's in UTC)
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            # Convert to CST
            cst_dt = dt.astimezone(self.cst_tz)
            
            # Format in military time
            return cst_dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.error(f"Error formatting timestamp {timestamp_str}: {e}")
            return timestamp_str
    
    def _get_system_status(self):
        """Get system status from database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get latest readings for each device
            cursor.execute("""
                SELECT device_name, MAX(timestamp) as last_reading
                FROM readings 
                GROUP BY device_name
            """)
            
            devices = {}
            for row in cursor.fetchall():
                device_name, last_reading = row
                # Consider device connected if it has a reading in the last 5 minutes
                last_reading_dt = datetime.fromisoformat(last_reading)
                connected = (datetime.now(self.cst_tz) - last_reading_dt) < timedelta(minutes=5)
                
                devices[device_name] = {
                    'connected': connected,
                    'last_reading': last_reading,
                    'last_reading_dt': last_reading_dt.isoformat()
                }
            
            conn.close()
            
            return {
                'timestamp': datetime.now(self.cst_tz).isoformat(),
                'devices': devices,
                'system_status': 'running'
            }
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                'timestamp': datetime.now(self.cst_tz).isoformat(),
                'devices': {},
                'system_status': 'error'
            }
    
    def _get_latest_readings(self):
        """Get latest temperature readings"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get latest temperature reading for each device
            cursor.execute("""
                SELECT device_name, value, timestamp
                FROM readings r1
                WHERE register_name = 'temperature'
                AND timestamp = (
                    SELECT MAX(timestamp) 
                    FROM readings r2 
                    WHERE r2.device_name = r1.device_name 
                    AND r2.register_name = 'temperature'
                )
            """)
            
            readings = {}
            for row in cursor.fetchall():
                device_name, value, timestamp = row
                
                # Debug: Log the raw timestamp format
                logger.info(f"Raw timestamp for {device_name}: {timestamp} (type: {type(timestamp)})")
                
                try:
                    last_reading_dt = datetime.fromisoformat(timestamp)
                    time_diff = datetime.now(self.cst_tz) - last_reading_dt
                    connected = time_diff < timedelta(minutes=5)
                    
                    # Debug logging
                    logger.info(f"Device {device_name}: last_reading={last_reading_dt}, now={datetime.now(self.cst_tz)}, diff={time_diff}, connected={connected}")
                    
                except ValueError as e:
                    logger.error(f"Error parsing timestamp for {device_name}: {timestamp}, error: {e}")
                    # If we can't parse the timestamp, assume disconnected
                    connected = False
                    last_reading_dt = None
                
                readings[device_name] = {
                    'temperature': value,
                    'timestamp': timestamp,
                    'connected': connected
                }
            
            conn.close()
            return readings
            
        except Exception as e:
            logger.error(f"Error getting latest readings: {e}")
            return {}
    
    def _get_historical_data(self, days=1):
        """Get historical data for the specified number of days"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get data from the last N days in CST
            start_date = datetime.now(self.cst_tz) - timedelta(days=days)
            
            cursor.execute("""
                SELECT device_name, value, timestamp
                FROM readings
                WHERE register_name = 'temperature'
                AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (start_date.isoformat(),))
            
            data = {}
            for row in cursor.fetchall():
                device_name, value, timestamp = row
                if device_name not in data:
                    data[device_name] = []
                
                # Convert timestamp to CST for display
                cst_timestamp = self._format_timestamp_cst(timestamp)
                
                data[device_name].append({
                    'temperature': value,
                    'timestamp': cst_timestamp
                })
            
            conn.close()
            return data
            
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            return {}
    
    def _get_device_info(self):
        """Get device information"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get device statistics for temperature readings
            cursor.execute("""
                SELECT device_name, 
                       COUNT(*) as reading_count,
                       MIN(timestamp) as first_reading,
                       MAX(timestamp) as last_reading,
                       AVG(value) as avg_temperature,
                       MIN(value) as min_temperature,
                       MAX(value) as max_temperature
                FROM readings
                WHERE register_name = 'temperature'
                GROUP BY device_name
            """)
            
            devices = []
            for row in cursor.fetchall():
                device_name, count, first, last, avg, min_temp, max_temp = row
                devices.append({
                    'name': device_name,
                    'reading_count': count,
                    'first_reading': first,
                    'last_reading': last,
                    'avg_temperature': round(avg, 1) if avg else None,
                    'min_temperature': min_temp,
                    'max_temperature': max_temp
                })
            
            conn.close()
            return {'devices': devices}
            
        except Exception as e:
            logger.error(f"Error getting device info: {e}")
            return {'devices': []}
    
    def _get_csv_data(self, device_name):
        """Generate CSV data for a specific device"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get all temperature readings for the device
            cursor.execute("""
                SELECT timestamp, value
                FROM readings
                WHERE device_name = ? AND register_name = 'temperature'
                ORDER BY timestamp DESC
            """, (device_name,))
            
            # Create CSV in memory
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp', 'Temperature (°F)'])
            
            for row in cursor.fetchall():
                timestamp, value = row
                # Convert timestamp to CST for CSV
                cst_timestamp = self._format_timestamp_cst(timestamp)
                writer.writerow([cst_timestamp, value])
            
            conn.close()
            
            # Return CSV file using BytesIO
            output.seek(0)
            csv_data = output.getvalue().encode('utf-8')
            return send_file(
                BytesIO(csv_data),
                mimetype='text/csv',
                as_attachment=True,
                download_name=f'{device_name}_data_{datetime.now().strftime("%Y%m%d")}.csv'
            )
            
        except Exception as e:
            logger.error(f"Error generating CSV for {device_name}: {e}")
            return jsonify({'error': str(e)}), 500
    
    def _cleanup_duplicate_readings(self):
        """Clean up duplicate readings with the same timestamp"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Find and delete duplicate readings
            cursor.execute("""
                DELETE FROM readings 
                WHERE id NOT IN (
                    SELECT MIN(id) 
                    FROM readings 
                    GROUP BY device_name, register_name, timestamp
                )
            """)
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} duplicate readings")
            return {
                'success': True,
                'deleted_count': deleted_count,
                'message': f'Cleaned up {deleted_count} duplicate readings'
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up duplicates: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_storage_info(self):
        """Get comprehensive storage usage information"""
        try:
            # Get system storage information
            disk_usage = shutil.disk_usage(os.path.dirname(self.db_path))
            
            # Get database size and statistics
            db_size = 0
            record_count = 0
            oldest_record = None
            newest_record = None
            
            if os.path.exists(self.db_path):
                db_size = os.path.getsize(self.db_path)
                
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Get record count
                cursor.execute("SELECT COUNT(*) FROM readings")
                record_count = cursor.fetchone()[0]
                
                # Get oldest and newest records
                if record_count > 0:
                    cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM readings")
                    oldest, newest = cursor.fetchone()
                    if oldest:
                        oldest_record = self._format_timestamp_cst(oldest)
                    if newest:
                        newest_record = self._format_timestamp_cst(newest)
                
                conn.close()
            
            # Calculate data consumption
            daily_consumption = self._calculate_data_consumption(1)
            weekly_consumption = self._calculate_data_consumption(7)
            monthly_consumption = self._calculate_data_consumption(30)
            
            # Calculate average daily consumption (last 30 days)
            avg_daily_consumption = monthly_consumption / 30 if monthly_consumption > 0 else 0
            
            return {
                'system_storage': {
                    'total': disk_usage.total,
                    'used': disk_usage.used,
                    'available': disk_usage.free
                },
                'database_size': db_size,
                'record_count': record_count,
                'oldest_record': oldest_record or 'N/A',
                'newest_record': newest_record or 'N/A',
                'daily_consumption': daily_consumption,
                'weekly_consumption': weekly_consumption,
                'monthly_consumption': monthly_consumption,
                'avg_daily_consumption': avg_daily_consumption
            }
            
        except Exception as e:
            logger.error(f"Error getting storage info: {e}")
            return {
                'system_storage': {'total': 0, 'used': 0, 'available': 0},
                'database_size': 0,
                'record_count': 0,
                'oldest_record': 'N/A',
                'newest_record': 'N/A',
                'daily_consumption': 0,
                'weekly_consumption': 0,
                'monthly_consumption': 0,
                'avg_daily_consumption': 0
            }
    
    def _calculate_data_consumption(self, days):
        """Calculate data consumption for the specified number of days"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get data from the last N days
            start_date = datetime.now(self.cst_tz) - timedelta(days=days)
            
            cursor.execute("""
                SELECT COUNT(*) as record_count
                FROM readings
                WHERE timestamp >= ?
            """, (start_date.isoformat(),))
            
            record_count = cursor.fetchone()[0]
            conn.close()
            
            # Estimate data size (rough calculation)
            # Each record: ~100 bytes (timestamp, device_name, register_name, value)
            estimated_size = record_count * 100
            
            return estimated_size
            
        except Exception as e:
            logger.error(f"Error calculating data consumption: {e}")
            return 0
    
    def _generate_report(self):
        """Generate a work order report"""
        try:
            if not self.report_generator:
                return {"error": "Report generator not available"}
            
            data = request.get_json()
            if not data:
                return {"error": "No data provided"}
            
            # Extract parameters
            work_order_number = data.get('work_order_number', 'WO-UNKNOWN')
            start_time_str = data.get('start_time')
            end_time_str = data.get('end_time')
            machine_id = data.get('machine_id', 'Line-07')
            output_format = data.get('output_format', 'pdf')
            
            # Validate required fields
            if not start_time_str or not end_time_str:
                return {"error": "Start time and end time are required"}
            
            try:
                # Parse the datetime strings from datetime-local input
                # datetime-local inputs are in the user's local timezone
                start_time = datetime.fromisoformat(start_time_str)
                end_time = datetime.fromisoformat(end_time_str)
                
                # Convert to CST timezone for consistency with stored data
                # We need to assume the input times are in CST since that's what we're using throughout
                import pytz
                cst_tz = pytz.timezone('America/Chicago')
                start_time = cst_tz.localize(start_time)
                end_time = cst_tz.localize(end_time)
                
                logger.info(f"Report time range: {start_time} to {end_time}")
                
            except ValueError as e:
                return {"error": f"Invalid date format: {e}"}
            
            # Generate report
            report_metadata = self.report_generator.generate_work_order_report(
                work_order_number=work_order_number,
                start_time=start_time,
                end_time=end_time,
                machine_id=machine_id,
                output_format=output_format
            )
            
            return {
                "success": True,
                "report": report_metadata
            }
            
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return {"error": str(e)}
    
    def _get_report_history(self, limit=50):
        """Get report history"""
        try:
            if not self.report_generator:
                return {"error": "Report generator not available"}
            
            history = self.report_generator.get_report_history(limit)
            return {
                "success": True,
                "reports": history
            }
            
        except Exception as e:
            logger.error(f"Error getting report history: {e}")
            return {"error": str(e)}
    
    def _download_report(self, report_id):
        """Download a specific report"""
        try:
            if not self.report_generator:
                return jsonify({"error": "Report generator not available"})
            
            # Get report metadata
            history = self.report_generator.get_report_history(1000)
            report_metadata = None
            
            for report in history:
                if report.get('report_id') == report_id:
                    report_metadata = report
                    break
            
            if not report_metadata:
                return jsonify({"error": "Report not found"})
            
            file_path = report_metadata.get('file_path')
            if not file_path or not os.path.exists(file_path):
                return jsonify({"error": "Report file not found"})
            
            # Determine file type
            if file_path.endswith('.pdf'):
                mimetype = 'application/pdf'
            elif file_path.endswith('.txt'):
                mimetype = 'text/plain'
            else:
                mimetype = 'application/octet-stream'
            
            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=True,
                download_name=os.path.basename(file_path)
            )
            
        except Exception as e:
            logger.error(f"Error downloading report: {e}")
            return jsonify({"error": str(e)})
    
    def _export_report_csv(self, report_id):
        """Export report data to CSV"""
        try:
            if not self.report_generator:
                return jsonify({"error": "Report generator not available"})
            
            csv_path = self.report_generator.export_report_csv(report_id)
            
            return send_file(
                csv_path,
                mimetype='text/csv',
                as_attachment=True,
                download_name=f"report_data_{report_id}.csv"
            )
            
        except Exception as e:
            logger.error(f"Error exporting CSV: {e}")
            return jsonify({"error": str(e)})
    
    def start(self):
        """Start the web server"""
        logger.info(f"Starting Vulcan Sentinel web server on {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False, threaded=True)
    
    def stop(self):
        """Stop the web server"""
        logger.info("Stopping Vulcan Sentinel web server")
        # Flask doesn't have a built-in stop method, but we can handle this in the main app 