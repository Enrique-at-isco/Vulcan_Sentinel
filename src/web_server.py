"""
Web server for Vulcan Sentinel

Provides a web interface for viewing:
- Real-time temperature data
- Historical data
- System status
- CSV downloads
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

logger = logging.getLogger(__name__)

class VulcanSentinelWebServer:
    """Flask web server for Vulcan Sentinel"""
    
    def __init__(self, db_path="data/vulcan_sentinel.db", host="0.0.0.0", port=8080):
        self.db_path = db_path
        self.host = host
        self.port = port
        self.app = Flask(__name__)
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
    
    def _get_dashboard(self):
        """Generate dashboard HTML"""
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
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Vulcan Sentinel Dashboard</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
                    .container {{ max-width: 1200px; margin: 0 auto; }}
                    .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }}
                    .header h1 {{ margin: 0; font-size: 2.5em; }}
                    .header p {{ margin: 5px 0 0 0; opacity: 0.9; }}
                    .status-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 20px; }}
                    .status-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    .status-card h3 {{ margin: 0 0 15px 0; color: #333; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
                    .temperature {{ font-size: 3em; font-weight: bold; color: #667eea; text-align: center; margin: 10px 0; }}
                    .device-info {{ display: flex; justify-content: space-between; margin: 5px 0; }}
                    .device-info span:first-child {{ font-weight: bold; }}
                    .connected {{ color: #28a745; }}
                    .disconnected {{ color: #dc3545; }}
                    .actions {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                    .actions h3 {{ margin: 0 0 15px 0; color: #333; }}
                    .btn {{ display: inline-block; padding: 10px 20px; margin: 5px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; }}
                    .btn:hover {{ background: #5a6fd8; }}
                    .refresh {{ text-align: right; margin-bottom: 10px; }}
                    .refresh-btn {{ background: #28a745; border: none; color: white; padding: 10px 20px; border-radius: 5px; cursor: pointer; }}
                                         .refresh-btn:hover {{ background: #218838; }}
                     .chart-container {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                     .chart-container h3 {{ margin: 0 0 15px 0; color: #333; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
                     .chart-wrapper {{ position: relative; height: 400px; }}
                 </style>
                 <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
                 <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns"></script>
             </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🔥 Vulcan Sentinel</h1>
                        <p>Industrial Temperature Monitoring System</p>
                    </div>
                    
                                         <div class="refresh">
                         <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Data</button>
                         <button class="refresh-btn" onclick="cleanupDuplicates()" style="background: #dc3545; margin-left: 10px;">🧹 Clean Duplicates</button>
                     </div>
                    
                    <div class="status-grid">
                        <div class="status-card">
                            <h3>🌡️ Current Temperatures</h3>
            """
            
            # Add temperature readings
            for device_name, data in readings.items():
                if data.get('connected'):
                    temp = data.get('temperature', 'N/A')
                    html += f"""
                            <div style="margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                                <div style="font-weight: bold; color: #333;">{device_name.replace('_', ' ').title()}</div>
                                <div class="temperature">{temp}°F</div>
                                                                 <div style="text-align: center; color: #666; font-size: 0.9em;">Last updated: {self._format_timestamp_cst(data.get('timestamp', 'N/A'))}</div>
                            </div>
                    """
                else:
                    html += f"""
                            <div style="margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                                <div style="font-weight: bold; color: #333;">{device_name.replace('_', ' ').title()}</div>
                                <div style="text-align: center; color: #dc3545; font-size: 1.2em;">⚠️ Disconnected</div>
                            </div>
                    """
            
            html += """
                        </div>
                        
                        <div class="status-card">
                            <h3>📊 System Status</h3>
            """
            
            # Add system status
            for device_name, data in status.get('devices', {}).items():
                status_class = "connected" if data.get('connected') else "disconnected"
                status_text = "🟢 Connected" if data.get('connected') else "🔴 Disconnected"
                html += f"""
                            <div class="device-info">
                                <span>{device_name.replace('_', ' ').title()}:</span>
                                <span class="{status_class}">{status_text}</span>
                            </div>
                """
            
            html += f"""
                            <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee;">
                                <div class="device-info">
                                    <span>System Status:</span>
                                    <span class="connected">🟢 Running</span>
                                </div>
                                                                 <div class="device-info">
                                     <span>Last Update:</span>
                                     <span>{datetime.now(self.cst_tz).strftime('%Y-%m-%d %H:%M:%S')}</span>
                                 </div>
                            </div>
                        </div>
                                         </div>
                     
                     <div class="chart-container">
                         <h3>📈 Temperature Time Series</h3>
                         <div class="chart-wrapper">
                             <canvas id="temperatureChart"></canvas>
                         </div>
                     </div>
                     
                     <div class="actions">
                         <h3>📥 Data Export</h3>
                         <a href="/api/csv/preheat" class="btn">📄 Preheat CSV</a>
                         <a href="/api/csv/main_heat" class="btn">📄 Main Heat CSV</a>
                         <a href="/api/csv/rib_heat" class="btn">📄 Rib Heat CSV</a>
                         <a href="/api/readings/history?days=7" class="btn">📊 7-Day History</a>
                         <a href="/api/readings/history?days=30" class="btn">📊 30-Day History</a>
                     </div>
                 </div>
                
                                 <script>
                     // Chart configuration
                     const chartColors = {{
                         preheat: 'rgba(255, 99, 132, 1)',
                         main_heat: 'rgba(54, 162, 235, 1)',
                         rib_heat: 'rgba(75, 192, 192, 1)'
                     }};
                     
                     const chartBorderColors = {{
                         preheat: 'rgba(255, 99, 132, 0.8)',
                         main_heat: 'rgba(54, 162, 235, 0.8)',
                         rib_heat: 'rgba(75, 192, 192, 0.8)'
                     }};
                     
                     // Initialize chart
                     const ctx = document.getElementById('temperatureChart').getContext('2d');
                     const temperatureChart = new Chart(ctx, {{
                         type: 'line',
                         data: {{
                             labels: [],
                             datasets: [
                                 {{
                                     label: 'Preheat',
                                     data: [],
                                     borderColor: chartColors.preheat,
                                     backgroundColor: chartBorderColors.preheat,
                                     borderWidth: 2,
                                     fill: false,
                                     tension: 0.1
                                 }},
                                 {{
                                     label: 'Main Heat',
                                     data: [],
                                     borderColor: chartColors.main_heat,
                                     backgroundColor: chartBorderColors.main_heat,
                                     borderWidth: 2,
                                     fill: false,
                                     tension: 0.1
                                 }},
                                 {{
                                     label: 'Rib Heat',
                                     data: [],
                                     borderColor: chartColors.rib_heat,
                                     backgroundColor: chartBorderColors.rib_heat,
                                     borderWidth: 2,
                                     fill: false,
                                     tension: 0.1
                                 }}
                             ]
                         }},
                         options: {{
                             responsive: true,
                             maintainAspectRatio: false,
                             plugins: {{
                                 title: {{
                                     display: true,
                                     text: 'Temperature Readings Over Time'
                                 }},
                                 legend: {{
                                     display: true,
                                     position: 'top'
                                 }}
                             }},
                             scales: {{
                                 x: {{
                                     type: 'time',
                                     time: {{
                                         unit: 'hour',
                                         displayFormats: {{
                                             hour: 'MMM dd, HH:mm'
                                         }}
                                     }},
                                     title: {{
                                         display: true,
                                         text: 'Time'
                                     }}
                                 }},
                                 y: {{
                                     title: {{
                                         display: true,
                                         text: 'Temperature (°F)'
                                     }},
                                     beginAtZero: false
                                 }}
                             }},
                             interaction: {{
                                 intersect: false,
                                 mode: 'index'
                             }}
                         }}
                     }});
                     
                     // Function to update chart data
                     async function updateChartData() {{
                         try {{
                             const response = await fetch('/api/readings/history?days=1');
                             const data = await response.json();
                             
                             // Clear existing data
                             temperatureChart.data.labels = [];
                             temperatureChart.data.datasets.forEach(dataset => {{
                                 dataset.data = [];
                             }});
                             
                             // Process data for each device
                             const deviceData = {{
                                 preheat: [],
                                 main_heat: [],
                                 rib_heat: []
                             }};
                             
                             // Collect data points
                             Object.keys(data).forEach(deviceName => {{
                                 if (data[deviceName] && Array.isArray(data[deviceName])) {{
                                     data[deviceName].forEach(reading => {{
                                         const timestamp = new Date(reading.timestamp);
                                         const temp = reading.temperature;
                                         
                                         if (deviceName === 'preheat') {{
                                             deviceData.preheat.push({{x: timestamp, y: temp}});
                                         }} else if (deviceName === 'main_heat') {{
                                             deviceData.main_heat.push({{x: timestamp, y: temp}});
                                         }} else if (deviceName === 'rib_heat') {{
                                             deviceData.rib_heat.push({{x: timestamp, y: temp}});
                                         }}
                                     }});
                                 }}
                             }});
                             
                             // Sort data by timestamp
                             Object.keys(deviceData).forEach(device => {{
                                 deviceData[device].sort((a, b) => a.x - b.x);
                             }});
                             
                             // Update chart datasets
                             temperatureChart.data.datasets[0].data = deviceData.preheat;
                             temperatureChart.data.datasets[1].data = deviceData.main_heat;
                             temperatureChart.data.datasets[2].data = deviceData.rib_heat;
                             
                             temperatureChart.update();
                             
                         }} catch (error) {{
                             console.error('Error updating chart data:', error);
                         }}
                     }}
                     
                     // Load chart data on page load
                     updateChartData();
                     
                     // Auto-refresh chart data every 30 seconds
                     setInterval(updateChartData, 30000);
                     
                     // Auto-refresh page every 5 minutes
                     setTimeout(function() {{
                         location.reload();
                     }}, 300000);
                     
                     // Function to cleanup duplicate readings
                     async function cleanupDuplicates() {{
                         if (confirm('Are you sure you want to clean up duplicate readings? This cannot be undone.')) {{
                             try {{
                                 const response = await fetch('/api/cleanup-duplicates');
                                 const result = await response.json();
                                 
                                 if (result.success) {{
                                     alert(`Success: ${{result.message}}`);
                                     location.reload();
                                 }} else {{
                                     alert(`Error: ${{result.error}}`);
                                 }}
                             }} catch (error) {{
                                 console.error('Error cleaning up duplicates:', error);
                                 alert('Error cleaning up duplicates');
                             }}
                         }}
                     }}
                 </script>
            </body>
            </html>
            """
            
            return html
            
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
                connected = (datetime.now() - last_reading_dt) < timedelta(minutes=5)
                
                devices[device_name] = {
                    'connected': connected,
                    'last_reading': last_reading,
                    'last_reading_dt': last_reading_dt.isoformat()
                }
            
            conn.close()
            
            return {
                'timestamp': datetime.now().isoformat(),
                'devices': devices,
                'system_status': 'running'
            }
            
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                'timestamp': datetime.now().isoformat(),
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
                last_reading_dt = datetime.fromisoformat(timestamp)
                connected = (datetime.now() - last_reading_dt) < timedelta(minutes=5)
                
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
    
    def start(self):
        """Start the web server"""
        logger.info(f"Starting Vulcan Sentinel web server on {self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=False, threaded=True)
    
    def stop(self):
        """Stop the web server"""
        logger.info("Stopping Vulcan Sentinel web server")
        # Flask doesn't have a built-in stop method, but we can handle this in the main app 