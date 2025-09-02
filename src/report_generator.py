"""
Report Generator for Vulcan Sentinel

Handles generation of work order reports in both thermal receipt and PDF formats.
Includes temperature time series plots, process data, and trigger events.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import sqlite3
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.figure import Figure
import numpy as np
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io
import hashlib
import uuid
import pytz
import csv

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates work order reports in multiple formats"""
    
    def __init__(self, db_manager, config_manager):
        self.db_manager = db_manager
        self.config_manager = config_manager
        # Use absolute path for reports directory to match container structure
        self.reports_dir = "/app/reports"
        self._ensure_reports_directory()
        self.report_counter = self._load_report_counter()
        
        # Set timezone to CST to match other components
        self.cst_tz = pytz.timezone('America/Chicago')
        
    def _ensure_reports_directory(self):
        """Ensure reports directory exists"""
        os.makedirs(self.reports_dir, exist_ok=True)
        
    def _load_report_counter(self) -> int:
        """Load the current report counter from file"""
        counter_file = os.path.join(self.reports_dir, "report_counter.json")
        try:
            if os.path.exists(counter_file):
                with open(counter_file, 'r') as f:
                    data = json.load(f)
                    return data.get('counter', 0)
        except Exception as e:
            logger.error(f"Failed to load report counter: {e}")
        return 0
        
    def _save_report_counter(self):
        """Save the current report counter to file"""
        counter_file = os.path.join(self.reports_dir, "report_counter.json")
        try:
            with open(counter_file, 'w') as f:
                json.dump({'counter': self.report_counter}, f)
        except Exception as e:
            logger.error(f"Failed to save report counter: {e}")
            
    def _get_next_report_id(self) -> str:
        """Get the next sequential report ID"""
        self.report_counter += 1
        self._save_report_counter()
        return f"{self.report_counter:06d}"
        
    def generate_work_order_report(self, 
                                 work_order_number: str,
                                 start_time: datetime,
                                 end_time: datetime,
                                 machine_id: str = "Line-07",
                                 output_format: str = "pdf") -> Dict[str, Any]:
        """
        Generate a complete work order report
        
        Args:
            work_order_number: Unique work order identifier
            start_time: Process start time
            end_time: Process end time
            machine_id: Machine/Line identifier
            output_format: 'pdf' or 'thermal'
            
        Returns:
            Dictionary with report metadata and file paths
        """
        try:
            # Generate report ID
            report_id = self._get_next_report_id()
            
            # Get process data
            process_data = self._get_process_data(start_time, end_time)
            
            # Generate temperature plot
            plot_path = self._generate_temperature_plot(process_data, report_id)
            
            # Create report content
            report_content = self._create_report_content(
                work_order_number, start_time, end_time, machine_id,
                process_data, report_id
            )
            
            # Generate output file
            if output_format.lower() == "pdf":
                output_path = self._generate_pdf_report(report_content, plot_path, report_id)
            else:
                output_path = self._generate_thermal_report(report_content, report_id)
                
            # Create report metadata
            report_metadata = {
                'report_id': report_id,
                'work_order_number': work_order_number,
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'machine_id': machine_id,
                'output_format': output_format,
                'file_path': output_path,
                'generated_at': datetime.now(self.cst_tz).isoformat(),
                'digital_signature': self._generate_digital_signature(report_content)
            }
            
            # Save metadata
            self._save_report_metadata(report_metadata)
            
            logger.info(f"Generated report {report_id} for work order {work_order_number}")
            return report_metadata
            
        except Exception as e:
            logger.error(f"Failed to generate work order report: {e}")
            raise
            
    def _get_process_data(self, start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Get all process data for the specified time range"""
        try:
            # Get device configurations
            devices_config = self.config_manager.load_devices_config()
            
            process_data = {
                'sensors': {},
                'trigger_events': [],
                'manual_overrides': [],
                'run_duration': (end_time - start_time).total_seconds()
            }
            
            # Define all expected sensors
            all_sensors = ['preheat', 'main_heat', 'rib_heat']
            
            # Get data for each sensor
            for device_id, device_config in devices_config['devices'].items():
                sensor_name = device_config['name']
                logger.info(f"Fetching data for sensor {sensor_name} from {start_time} to {end_time}")
                
                readings = self.db_manager.get_readings_range(
                    sensor_name, start_time, end_time
                )
                
                logger.info(f"Found {len(readings)} readings for {sensor_name}")
                
                if readings:
                    process_data['sensors'][sensor_name] = {
                        'readings': readings,
                        'statistics': self._calculate_sensor_statistics(readings),
                        'setpoints': self._get_setpoints(sensor_name),
                        'stages': self._identify_heat_stages(readings)
                    }
                else:
                    # Include sensor with no data
                    process_data['sensors'][sensor_name] = {
                        'readings': [],
                        'statistics': {},
                        'setpoints': self._get_setpoints(sensor_name),
                        'stages': []
                    }
            
            # Ensure all expected sensors are included, even if not in device config
            for sensor_name in all_sensors:
                if sensor_name not in process_data['sensors']:
                    process_data['sensors'][sensor_name] = {
                        'readings': [],
                        'statistics': {},
                        'setpoints': self._get_setpoints(sensor_name),
                        'stages': []
                    }
                    
            # Get trigger events
            process_data['trigger_events'] = self._get_trigger_events(start_time, end_time)
            
            # Get manual overrides
            process_data['manual_overrides'] = self._get_manual_overrides(start_time, end_time)
            
            return process_data
            
        except Exception as e:
            logger.error(f"Failed to get process data: {e}")
            return {}
            
    def _calculate_sensor_statistics(self, readings: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate statistics for sensor readings"""
        if not readings:
            return {}
            
        values = [r['value'] for r in readings]
        return {
            'average': np.mean(values),
            'minimum': np.min(values),
            'maximum': np.max(values),
            'duration': len(readings) * 20  # Assuming 20-second intervals
        }
        
    def _get_setpoints(self, sensor_name: str) -> Dict[str, float]:
        """Get temperature setpoints for a sensor from database"""
        try:
            # Try to get setpoint from database first
            setpoint_data = self.db_manager.get_setpoint(sensor_name)
            if setpoint_data:
                return {
                    'set_temp': setpoint_data['setpoint_value'],
                    'deviation': setpoint_data['deviation']
                }
        except Exception as e:
            logger.error(f"Failed to get setpoint from database for {sensor_name}: {e}")
        
        # Fallback to default values if database lookup fails
        default_setpoints = {
            'preheat': {'set_temp': 300, 'deviation': 5},
            'main_heat': {'set_temp': 400, 'deviation': 5},
            'rib_heat': {'set_temp': 350, 'deviation': 5}
        }
        return default_setpoints.get(sensor_name, {'set_temp': 0, 'deviation': 0})
        
    def _identify_heat_stages(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify different heat stages from temperature data"""
        if not readings:
            return []
            
        stages = []
        current_stage = None
        stage_start = None
        
        for i, reading in enumerate(readings):
            temp = reading['value']
            timestamp = datetime.fromisoformat(reading['timestamp'])
            
            # Simple stage detection based on temperature ranges
            if temp < 150:
                stage_name = "Preheat"
            elif temp < 300:
                stage_name = "Main Heat"
            else:
                stage_name = "Rib Heat"
                
            if current_stage != stage_name:
                if current_stage and stage_start:
                    stages.append({
                        'name': current_stage,
                        'start_time': stage_start,
                        'end_time': timestamp,
                        'duration': (timestamp - stage_start).total_seconds()
                    })
                current_stage = stage_name
                stage_start = timestamp
                
        # Add final stage
        if current_stage and stage_start and readings:
            stages.append({
                'name': current_stage,
                'start_time': stage_start,
                'end_time': readings[-1]['timestamp'],
                'duration': (datetime.fromisoformat(readings[-1]['timestamp']) - stage_start).total_seconds()
            })
            
        return stages
        
    def _get_trigger_events(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get trigger events for the time period"""
        try:
            events = self.db_manager.get_events(limit=1000)
            trigger_events = []
            
            for event in events:
                # Convert database timestamp to timezone-aware datetime
                event_time = datetime.fromisoformat(event['timestamp'])
                # Make it timezone-aware by localizing to CST
                event_time = self.cst_tz.localize(event_time)
                
                if start_time <= event_time <= end_time:
                    if 'trigger' in event['event_type'].lower() or 'stage' in event['event_type'].lower():
                        trigger_events.append({
                            'event': event['message'],
                            'timestamp': event_time.strftime('%H:%M:%S')
                        })
                        
            return trigger_events
            
        except Exception as e:
            logger.error(f"Failed to get trigger events: {e}")
            return []
            
    def _get_manual_overrides(self, start_time: datetime, end_time: datetime) -> List[Dict[str, Any]]:
        """Get manual override events for the time period"""
        try:
            events = self.db_manager.get_events(limit=1000)
            overrides = []
            
            for event in events:
                # Convert database timestamp to timezone-aware datetime
                event_time = datetime.fromisoformat(event['timestamp'])
                # Make it timezone-aware by localizing to CST
                event_time = self.cst_tz.localize(event_time)
                
                if start_time <= event_time <= end_time:
                    if 'override' in event['event_type'].lower() or 'manual' in event['event_type'].lower():
                        overrides.append({
                            'sensor': event.get('device_name', 'Unknown'),
                            'action': event['message'],
                            'timestamp': event_time.strftime('%H:%M:%S')
                        })
                        
            return overrides
            
        except Exception as e:
            logger.error(f"Failed to get manual overrides: {e}")
            return []
            
    def _generate_temperature_plot(self, process_data: Dict[str, Any], report_id: str) -> str:
        """Generate temperature time series plot with different line styles for black and white printing"""
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            # Define line styles for black and white printing
            line_styles = {
                'preheat': ('solid', 2),
                'main_heat': ('dashed', 2),
                'rib_heat': ('dotted', 2)
            }
            
            # Always include all three sensors, even if no data
            all_sensors = ['preheat', 'main_heat', 'rib_heat']
            
            for sensor_name in all_sensors:
                sensor_data = process_data['sensors'].get(sensor_name, {})
                
                if 'readings' in sensor_data and sensor_data['readings']:
                    timestamps = [datetime.fromisoformat(r['timestamp']) for r in sensor_data['readings']]
                    temperatures = [r['value'] for r in sensor_data['readings']]
                    
                    linestyle, linewidth = line_styles.get(sensor_name, ('solid', 2))
                    
                    ax.plot(timestamps, temperatures, 
                           label=sensor_name.replace('_', ' ').title(),
                           linestyle=linestyle,
                           linewidth=linewidth,
                           color='black')
                else:
                    # Add a placeholder line for sensors with no data to show in legend
                    # Use a dummy line that won't be visible but will appear in legend
                    linestyle, linewidth = line_styles.get(sensor_name, ('solid', 2))
                    
                    # Create a dummy line with no data points but with the correct style
                    ax.plot([], [], 
                           label=f"{sensor_name.replace('_', ' ').title()} (No Data)",
                           linestyle=linestyle,
                           linewidth=linewidth,
                           color='black',
                           alpha=0.5)
                    
                    # Add a note for sensors with no data
                    ax.text(0.02, 0.98 - (all_sensors.index(sensor_name) * 0.05), 
                           f"{sensor_name.replace('_', ' ').title()}: No data available",
                           transform=ax.transAxes, fontsize=10, style='italic',
                           bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgray", alpha=0.7))
                           
            ax.set_xlabel('Time')
            ax.set_ylabel('Temperature (°F)')
            ax.set_title('Temperature Time Series')
            ax.legend()
            ax.grid(True, alpha=0.3)
            
            # Format x-axis
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            plt.xticks(rotation=45)
            
            # Save plot
            plot_path = os.path.join(self.reports_dir, f"temp_plot_{report_id}.png")
            plt.tight_layout()
            plt.savefig(plot_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            return plot_path
            
        except Exception as e:
            logger.error(f"Failed to generate temperature plot: {e}")
            return ""
            
    def _create_report_content(self, work_order_number: str, start_time: datetime, 
                             end_time: datetime, machine_id: str, 
                             process_data: Dict[str, Any], report_id: str) -> Dict[str, Any]:
        """Create the complete report content structure"""
        run_duration_seconds = process_data.get('run_duration', 0)
        
        return {
            'header': {
                'work_order_number': work_order_number,
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%H:%M:%S'),
                'machine_id': machine_id
            },
            'process_summary': {
                'run_duration': self._format_duration(run_duration_seconds),  # Format as HH:MM:SS
                'sensors': process_data.get('sensors', {})
            },
            'key_process_data': {
                'temperature_data': self._format_temperature_data(process_data),
                'setpoints': self._format_setpoints_data(process_data, start_time, end_time),
                'trigger_events': process_data.get('trigger_events', [])
            },
            'manual_overrides': process_data.get('manual_overrides', []),
            'footer': {
                'report_id': report_id,
                'generated_at': datetime.now(self.cst_tz).strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
    def _format_temperature_data(self, process_data: Dict[str, Any]) -> List[List[str]]:
        """Format temperature data for table display"""
        table_data = [['Stage', 'Avg Temp (°F)', 'Min Temp (°F)', 'Max Temp (°F)', 'Duration']]
        
        # Ensure all sensors are included in order
        all_sensors = ['preheat', 'main_heat', 'rib_heat']
        
        for sensor_name in all_sensors:
            sensor_data = process_data.get('sensors', {}).get(sensor_name, {})
            
            if 'statistics' in sensor_data and sensor_data['statistics']:
                stats = sensor_data['statistics']
                duration_str = self._format_duration(stats.get('duration', 0))
                
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    f"{stats.get('average', 0):.1f}",
                    f"{stats.get('minimum', 0):.1f}",
                    f"{stats.get('maximum', 0):.1f}",
                    duration_str
                ])
            else:
                # Show "No Data" for sensors without readings
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    "No Data",
                    "No Data",
                    "No Data",
                    "00:00:00"
                ])
                
        return table_data
        
    def _format_duration(self, duration_seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS format"""
        try:
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            seconds = int(duration_seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except (ValueError, TypeError):
            return "00:00:00"
        
    def _format_setpoints_data(self, process_data: Dict[str, Any], start_time: datetime = None, end_time: datetime = None) -> List[List[str]]:
        """Format setpoints data for table display with dynamic deviation calculation"""
        table_data = [['Stage', 'Set Temp (°F)', '+Dev', '-Dev']]
        
        # Ensure all sensors are included in order
        all_sensors = ['preheat', 'main_heat', 'rib_heat']
        
        for sensor_name in all_sensors:
            sensor_data = process_data.get('sensors', {}).get(sensor_name, {})
            
            if 'setpoints' in sensor_data:
                setpoints = sensor_data['setpoints']
                dev = setpoints.get('deviation', 0)
                
                # Calculate dynamic deviation only during report generation (when time parameters are provided)
                if start_time and end_time:
                    logger.info(f"Calculating dynamic deviation for {sensor_name} during report generation")
                    dev = self._calculate_dynamic_setpoint_deviation(sensor_name, start_time, end_time)
                
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    f"{setpoints.get('set_temp', 0)}",
                    f"+{dev}",
                    f"-{dev}"
                ])
            else:
                # Get current setpoint from database
                setpoint_data = self.db_manager.get_setpoint(sensor_name)
                set_temp = setpoint_data.get('setpoint_value', 0) if setpoint_data else 0
                
                # Use deviation from database or fallback to 5.0 if None
                dev = setpoint_data.get('deviation', 5.0) if setpoint_data else 5.0
                if dev is None:
                    dev = 5.0  # Default fallback
                
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    f"{set_temp}",
                    f"+{dev}",
                    f"-{dev}"
                ])
                
        return table_data
        
    def _calculate_dynamic_setpoint_deviation(self, sensor_name: str, start_time: datetime, end_time: datetime) -> float:
        """
        Calculate dynamic setpoint deviation based on sensor data when temperature reaches setpoint.
        
        This method analyzes the temperature readings for a sensor during the specified time period
        and calculates the deviation based on how much the temperature varies from the setpoint
        once it reaches the setpoint temperature.
        
        The calculation range starts when temperature first equals the setpoint and continues until:
        1. The end of the report time period, OR
        2. The setpoint is decreased after the initial temperature=setpoint match
        
        Args:
            sensor_name: Name of the sensor (e.g., 'preheat', 'main_heat', 'rib_heat')
            start_time: Start time of the analysis period
            end_time: End time of the analysis period
            
        Returns:
            Calculated deviation value in degrees Fahrenheit
        """
        try:
            # Get the current setpoint for this sensor
            setpoint_data = self.db_manager.get_setpoint(sensor_name)
            if not setpoint_data:
                logger.warning(f"No setpoint data found for {sensor_name}, using default deviation")
                return 5.0  # Default deviation
            
            setpoint_temp = setpoint_data.get('setpoint_value', 0)
            if setpoint_temp <= 0:
                logger.warning(f"Invalid setpoint temperature for {sensor_name}: {setpoint_temp}")
                return 5.0  # Default deviation
            
            # Query temperature readings for this sensor during the time period
            readings = self.db_manager.get_readings_for_period(
                sensor_name, start_time, end_time
            )
            
            if not readings:
                logger.warning(f"No temperature readings found for {sensor_name} during specified period")
                return 5.0  # Default deviation
            
            # Sort readings by timestamp to ensure chronological order
            readings.sort(key=lambda x: x['timestamp'])
            
            # Find the first instance where temperature equals or exceeds setpoint
            first_setpoint_match_index = None
            initial_setpoint = setpoint_temp
            
            for i, reading in enumerate(readings):
                temp_value = reading.get(sensor_name, 0)
                if temp_value >= setpoint_temp:
                    first_setpoint_match_index = i
                    break
            
            if first_setpoint_match_index is None:
                logger.info(f"Temperature never reached setpoint for {sensor_name} during specified period")
                return 5.0  # Default deviation
            
            # Get setpoint history to track changes during the period
            setpoint_history = self.db_manager.get_setpoint_history(sensor_name, start_time, end_time)
            
            # Collect readings for deviation calculation
            deviation_readings = []
            current_setpoint = initial_setpoint
            setpoint_decreased = False
            
            for i in range(first_setpoint_match_index, len(readings)):
                reading = readings[i]
                temp_value = reading.get(sensor_name, 0)
                reading_timestamp = reading['timestamp']
                
                # Check if setpoint has been decreased after the first match
                # Look for setpoint changes that occurred after the first temperature=setpoint match
                for setpoint_change in setpoint_history:
                    if setpoint_change['timestamp'] > readings[first_setpoint_match_index]['timestamp']:
                        if setpoint_change['setpoint_value'] < current_setpoint:
                            # Setpoint was decreased, stop deviation calculation
                            setpoint_decreased = True
                            logger.info(f"Setpoint decreased for {sensor_name} from {current_setpoint}°F to {setpoint_change['setpoint_value']}°F, stopping deviation calculation")
                            break
                        current_setpoint = setpoint_change['setpoint_value']
                
                if setpoint_decreased:
                    break
                
                # Add this reading to deviation calculation
                deviation_readings.append(temp_value)
            
            if len(deviation_readings) < 5:  # Need at least 5 readings for meaningful deviation
                logger.info(f"Insufficient deviation readings for {sensor_name} ({len(deviation_readings)} readings)")
                return 5.0  # Default deviation
            
            # Calculate deviation based on temperature variation from setpoint
            deviations = [abs(temp - current_setpoint) for temp in deviation_readings]
            
            # Use 95th percentile of deviations to account for outliers
            deviations.sort()
            percentile_index = int(len(deviations) * 0.95)
            calculated_deviation = deviations[percentile_index] if percentile_index < len(deviations) else deviations[-1]
            
            # Ensure deviation is within reasonable bounds (1-20°F)
            calculated_deviation = max(1.0, min(20.0, calculated_deviation))
            
            # Update the database with the calculated deviation
            self.db_manager.update_setpoint_deviation(sensor_name, calculated_deviation)
            
            if setpoint_decreased:
                logger.info(f"Calculated and stored dynamic deviation for {sensor_name}: {calculated_deviation:.1f}°F "
                           f"(based on {len(deviation_readings)} readings, stopped due to setpoint decrease)")
            else:
                logger.info(f"Calculated and stored dynamic deviation for {sensor_name}: {calculated_deviation:.1f}°F "
                           f"(based on {len(deviation_readings)} readings from first setpoint match to end of period)")
            
            return round(calculated_deviation, 1)
            
        except Exception as e:
            logger.error(f"Error calculating dynamic setpoint deviation for {sensor_name}: {e}")
            return 5.0  # Default deviation
        
    def _generate_pdf_report(self, report_content: Dict[str, Any], plot_path: str, report_id: str) -> str:
        """Generate PDF report"""
        try:
            output_path = os.path.join(self.reports_dir, f"work_order_report_{report_id}.pdf")
            doc = SimpleDocTemplate(output_path, pagesize=letter)
            
            # Get styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=30,
                alignment=TA_CENTER
            )
            
            # Build story
            story = []
            
            # Header
            story.append(Paragraph("Work Order Report", title_style))
            story.append(Spacer(1, 12))
            
            # Header Information
            header_data = [
                ['Work Order Number:', report_content['header']['work_order_number']],
                ['Start Time:', report_content['header']['start_time']],
                ['End Time:', report_content['header']['end_time']],
                ['Machine / Line ID:', report_content['header']['machine_id']]
            ]
            
            header_table = Table(header_data, colWidths=[2*inch, 4*inch])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 20))
            
            # Process Summary
            story.append(Paragraph("Process Summary", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            summary_data = [
                ['Run Duration:', report_content['process_summary']['run_duration']]
            ]
            summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
            summary_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 20))
            
            # Temperature Plot
            if plot_path and os.path.exists(plot_path):
                story.append(Paragraph("Temperature Time Series", styles['Heading3']))
                story.append(Spacer(1, 12))
                img = Image(plot_path, width=6*inch, height=4*inch)
                story.append(img)
                story.append(Spacer(1, 20))
            
            # Key Process Data
            story.append(Paragraph("Key Process Data - Temperature Data", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            # Temperature Data Table
            temp_table = Table(report_content['key_process_data']['temperature_data'], 
                             colWidths=[1.5*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
            temp_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(temp_table)
            story.append(Spacer(1, 20))
            
            # Setpoints Table
            story.append(Paragraph("Temperature Setpoints & Deviations", styles['Heading3']))
            story.append(Spacer(1, 12))
            
            setpoints_table = Table(report_content['key_process_data']['setpoints'], 
                                  colWidths=[1.5*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            setpoints_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(setpoints_table)
            story.append(Spacer(1, 20))
            
            # Trigger Events
            if report_content['key_process_data']['trigger_events']:
                story.append(Paragraph("Trigger Events", styles['Heading3']))
                story.append(Spacer(1, 12))
                
                events_data = [['Event', 'Timestamp']]
                for event in report_content['key_process_data']['trigger_events']:
                    events_data.append([event['event'], event['timestamp']])
                    
                events_table = Table(events_data, colWidths=[4*inch, 2*inch])
                events_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(events_table)
                story.append(Spacer(1, 20))
            
            # Manual Overrides
            if report_content['manual_overrides']:
                story.append(Paragraph("Manual Overrides", styles['Heading2']))
                story.append(Spacer(1, 12))
                
                overrides_data = [['Sensor', 'Action', 'Timestamp']]
                for override in report_content['manual_overrides']:
                    overrides_data.append([
                        override['sensor'],
                        override['action'],
                        override['timestamp']
                    ])
                    
                overrides_table = Table(overrides_data, colWidths=[1.5*inch, 3*inch, 1.5*inch])
                overrides_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ]))
                story.append(overrides_table)
                story.append(Spacer(1, 20))
            
            # Footer
            story.append(Paragraph("Footer", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            # Get current date in CST
            current_date = datetime.now(self.cst_tz).strftime('%Y-%m-%d')
            
            footer_data = [
                ['Operator Signature:', ''],
                ['Date:', current_date],
                ['Digital Report ID:', report_content['footer']['report_id']]
            ]
            
            footer_table = Table(footer_data, colWidths=[2*inch, 4*inch])
            footer_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('LINEBELOW', (1, 0), (1, 0), 1, colors.black),
                ('LINEBELOW', (1, 1), (1, 1), 1, colors.black),
            ]))
            story.append(footer_table)
            
            # Build PDF
            doc.build(story)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate PDF report: {e}")
            raise
            
    def _generate_thermal_report(self, report_content: Dict[str, Any], report_id: str) -> str:
        """Generate thermal receipt format report"""
        try:
            output_path = os.path.join(self.reports_dir, f"thermal_report_{report_id}.txt")
            
            with open(output_path, 'w') as f:
                # Header
                f.write("=" * 48 + "\n")
                f.write("           WORK ORDER REPORT\n")
                f.write("=" * 48 + "\n\n")
                
                # Header Information
                f.write("HEADER INFORMATION:\n")
                f.write("-" * 20 + "\n")
                f.write(f"Work Order Number: {report_content['header']['work_order_number']}\n")
                f.write(f"Start Time: {report_content['header']['start_time']}\n")
                f.write(f"End Time: {report_content['header']['end_time']}\n")
                f.write(f"Machine / Line ID: {report_content['header']['machine_id']}\n\n")
                
                # Process Summary
                f.write("PROCESS SUMMARY:\n")
                f.write("-" * 16 + "\n")
                f.write(f"Run Duration: {report_content['process_summary']['run_duration']}\n\n")
                
                # Temperature Data
                f.write("KEY PROCESS DATA - TEMPERATURE DATA:\n")
                f.write("-" * 35 + "\n")
                
                # Temperature table
                temp_data = report_content['key_process_data']['temperature_data']
                f.write(f"{'Stage':<12} {'Avg':<8} {'Min':<8} {'Max':<8} {'Duration':<10}\n")
                f.write("-" * 48 + "\n")
                for row in temp_data[1:]:  # Skip header
                    f.write(f"{row[0]:<12} {row[1]:<8} {row[2]:<8} {row[3]:<8} {row[4]:<10}\n")
                f.write("\n")
                
                # Setpoints
                f.write("TEMPERATURE SETPOINTS & DEVIATIONS:\n")
                f.write("-" * 35 + "\n")
                setpoints_data = report_content['key_process_data']['setpoints']
                f.write(f"{'Stage':<12} {'Set Temp':<10} {'+Dev':<6} {'-Dev':<6}\n")
                f.write("-" * 36 + "\n")
                for row in setpoints_data[1:]:  # Skip header
                    f.write(f"{row[0]:<12} {row[1]:<10} {row[2]:<6} {row[3]:<6}\n")
                f.write("\n")
                
                # Trigger Events
                if report_content['key_process_data']['trigger_events']:
                    f.write("TRIGGER EVENTS:\n")
                    f.write("-" * 14 + "\n")
                    f.write(f"{'Event':<30} {'Timestamp':<10}\n")
                    f.write("-" * 42 + "\n")
                    for event in report_content['key_process_data']['trigger_events']:
                        f.write(f"{event['event']:<30} {event['timestamp']:<10}\n")
                    f.write("\n")
                
                # Manual Overrides
                if report_content['manual_overrides']:
                    f.write("MANUAL OVERRIDES:\n")
                    f.write("-" * 16 + "\n")
                    f.write(f"{'Sensor':<12} {'Action':<25} {'Timestamp':<10}\n")
                    f.write("-" * 49 + "\n")
                    for override in report_content['manual_overrides']:
                        f.write(f"{override['sensor']:<12} {override['action']:<25} {override['timestamp']:<10}\n")
                    f.write("\n")
                
                # Footer
                f.write("FOOTER:\n")
                f.write("-" * 7 + "\n")
                # Get current date in CST
                current_date = datetime.now(self.cst_tz).strftime('%Y-%m-%d')
                
                f.write("Operator Signature: _________________\n")
                f.write(f"Date: {current_date}\n")
                f.write(f"Digital Report ID: {report_content['footer']['report_id']}\n")
                f.write("\n")
                f.write("=" * 48 + "\n")
                
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate thermal report: {e}")
            raise
            
    def _generate_digital_signature(self, report_content: Dict[str, Any]) -> str:
        """Generate digital signature for report authenticity"""
        try:
            # Create a hash of the report content
            content_str = json.dumps(report_content, sort_keys=True, default=str)
            return hashlib.sha256(content_str.encode()).hexdigest()[:16]
        except Exception as e:
            logger.error(f"Failed to generate digital signature: {e}")
            return ""
            
    def _save_report_metadata(self, metadata: Dict[str, Any]):
        """Save report metadata to database"""
        try:
            metadata_file = os.path.join(self.reports_dir, "report_metadata.json")
            
            # Load existing metadata
            existing_metadata = []
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    existing_metadata = json.load(f)
                    
            # Add new metadata
            existing_metadata.append(metadata)
            
            # Save updated metadata
            with open(metadata_file, 'w') as f:
                json.dump(existing_metadata, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save report metadata: {e}")
            
    def get_report_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent report history"""
        try:
            metadata_file = os.path.join(self.reports_dir, "report_metadata.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                    
                # Sort by generation time (newest first)
                metadata.sort(key=lambda x: x.get('generated_at', ''), reverse=True)
                return metadata[:limit]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Failed to get report history: {e}")
            return []
            
    def export_report_csv(self, report_id: str) -> str:
        """Export report data to CSV format matching database readings table structure"""
        try:
            # Get report metadata to find the original parameters
            metadata_file = os.path.join(self.reports_dir, "report_metadata.json")
            
            if not os.path.exists(metadata_file):
                raise Exception("Report metadata not found")
                
            with open(metadata_file, 'r') as f:
                metadata_list = json.load(f)
            
            # Find the specific report
            report_metadata = None
            for metadata in metadata_list:
                if metadata.get('report_id') == report_id:
                    report_metadata = metadata
                    break
            
            if not report_metadata:
                raise Exception(f"Report {report_id} not found in metadata")
            
            # Extract the original parameters
            work_order_number = report_metadata.get('work_order_number', '')
            start_time_str = report_metadata.get('start_time', '')
            end_time_str = report_metadata.get('end_time', '')
            machine_id = report_metadata.get('machine_id', '')
            
            # Parse the timestamps
            start_time = datetime.fromisoformat(start_time_str)
            end_time = datetime.fromisoformat(end_time_str)
            
            # Query the database directly to get data in the readings table format
            csv_path = os.path.join(self.reports_dir, f"report_data_{report_id}.csv")
            
            # Connect to database and query the readings table directly
            conn = sqlite3.connect(self.db_manager.db_path)
            cursor = conn.cursor()
            
            # Convert datetime objects to date and time strings for the new schema
            start_date = start_time.strftime('%Y-%m-%d')
            start_time_str = start_time.strftime('%H:%M:%S')
            end_date = end_time.strftime('%Y-%m-%d')
            end_time_str = end_time.strftime('%H:%M:%S')
            
            # Query based on the new schema with date and timestamp columns
            if start_date == end_date:
                # Same day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE date = ? AND timestamp BETWEEN ? AND ?
                    ORDER BY date ASC, timestamp ASC
                """, (start_date, start_time_str, end_time_str))
            else:
                # Cross-day query
                cursor.execute("""
                    SELECT date, timestamp, preheat, main_heat, rib_heat
                    FROM readings
                    WHERE (date > ? OR (date = ? AND timestamp >= ?))
                    AND (date < ? OR (date = ? AND timestamp <= ?))
                    ORDER BY date ASC, timestamp ASC
                """, (start_date, start_date, start_time_str, end_date, end_date, end_time_str))
            
            rows = cursor.fetchall()
            conn.close()
            
            with open(csv_path, 'w', newline='') as f:
                writer = csv.writer(f)
                # Write header matching the database readings table structure
                writer.writerow(['date', 'timestamp', 'preheat', 'main_heat', 'rib_heat'])
                
                # Write data rows
                for row in rows:
                    date_str, time_str, preheat, main_heat, rib_heat = row
                    writer.writerow([
                        date_str,
                        time_str,
                        preheat if preheat is not None else '',
                        main_heat if main_heat is not None else '',
                        rib_heat if rib_heat is not None else ''
                    ])
                
            logger.info(f"CSV exported to {csv_path} with {len(rows)} rows")
            return csv_path
            
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            raise
    
    def _determine_stage(self, temperature: float, sensor_name: str) -> str:
        """Determine the heat stage based on temperature and sensor"""
        try:
            temp = float(temperature)
            
            # Basic stage determination logic
            if temp < 100:
                return "Preheat"
            elif temp < 200:
                return "Main Heat"
            elif temp < 300:
                return "Rib Heat"
            else:
                return "High Temp"
                
        except (ValueError, TypeError):
            return "Unknown"
