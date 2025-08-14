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

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates work order reports in multiple formats"""
    
    def __init__(self, db_manager, config_manager):
        self.db_manager = db_manager
        self.config_manager = config_manager
        self.reports_dir = os.path.join(os.getcwd(), "reports")
        self._ensure_reports_directory()
        self.report_counter = self._load_report_counter()
        
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
                'generated_at': datetime.now().isoformat(),
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
            
            # Get data for each sensor
            for device_id, device_config in devices_config['devices'].items():
                sensor_name = device_config['name']
                readings = self.db_manager.get_readings_range(
                    sensor_name, start_time, end_time
                )
                
                if readings:
                    process_data['sensors'][sensor_name] = {
                        'readings': readings,
                        'statistics': self._calculate_sensor_statistics(readings),
                        'setpoints': self._get_setpoints(sensor_name),
                        'stages': self._identify_heat_stages(readings)
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
        """Get temperature setpoints for a sensor"""
        # This would typically come from device configuration or database
        # For now, using default values based on sensor type
        setpoints = {
            'preheat': {'set_temp': 300, 'deviation': 5},
            'main_heat': {'set_temp': 400, 'deviation': 5},
            'rib_heat': {'set_temp': 350, 'deviation': 5}
        }
        return setpoints.get(sensor_name, {'set_temp': 0, 'deviation': 0})
        
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
        if current_stage and stage_start:
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
                event_time = datetime.fromisoformat(event['timestamp'])
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
                event_time = datetime.fromisoformat(event['timestamp'])
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
        """Generate temperature time series plot"""
        try:
            fig, ax = plt.subplots(figsize=(10, 6))
            
            colors_map = {
                'preheat': 'orange',
                'main_heat': 'red',
                'rib_heat': 'yellow'
            }
            
            for sensor_name, sensor_data in process_data['sensors'].items():
                if 'readings' in sensor_data:
                    timestamps = [datetime.fromisoformat(r['timestamp']) for r in sensor_data['readings']]
                    temperatures = [r['value'] for r in sensor_data['readings']]
                    
                    ax.plot(timestamps, temperatures, 
                           label=sensor_name.replace('_', ' ').title(),
                           color=colors_map.get(sensor_name, 'blue'),
                           linewidth=2)
                           
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
        run_duration = timedelta(seconds=process_data.get('run_duration', 0))
        
        return {
            'header': {
                'work_order_number': work_order_number,
                'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end_time': end_time.strftime('%H:%M:%S'),
                'machine_id': machine_id
            },
            'process_summary': {
                'run_duration': str(run_duration).split('.')[0],  # Remove microseconds
                'sensors': process_data.get('sensors', {})
            },
            'key_process_data': {
                'temperature_data': self._format_temperature_data(process_data),
                'setpoints': self._format_setpoints_data(process_data),
                'trigger_events': process_data.get('trigger_events', [])
            },
            'manual_overrides': process_data.get('manual_overrides', []),
            'footer': {
                'report_id': report_id,
                'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        }
        
    def _format_temperature_data(self, process_data: Dict[str, Any]) -> List[List[str]]:
        """Format temperature data for table display"""
        table_data = [['Stage', 'Avg Temp (°F)', 'Min Temp (°F)', 'Max Temp (°F)', 'Duration']]
        
        for sensor_name, sensor_data in process_data.get('sensors', {}).items():
            if 'statistics' in sensor_data:
                stats = sensor_data['statistics']
                duration_str = f"{int(stats.get('duration', 0)):02d}:{int((stats.get('duration', 0) % 60)):02d}"
                
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    f"{stats.get('average', 0):.1f}",
                    f"{stats.get('minimum', 0):.1f}",
                    f"{stats.get('maximum', 0):.1f}",
                    duration_str
                ])
                
        return table_data
        
    def _format_setpoints_data(self, process_data: Dict[str, Any]) -> List[List[str]]:
        """Format setpoints data for table display"""
        table_data = [['Stage', 'Set Temp (°F)', '+Dev', '-Dev']]
        
        for sensor_name, sensor_data in process_data.get('sensors', {}).items():
            if 'setpoints' in sensor_data:
                setpoints = sensor_data['setpoints']
                dev = setpoints.get('deviation', 0)
                
                table_data.append([
                    sensor_name.replace('_', ' ').title(),
                    f"{setpoints.get('set_temp', 0)}",
                    f"+{dev}",
                    f"-{dev}"
                ])
                
        return table_data
        
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
            
            footer_data = [
                ['Operator Signature:', ''],
                ['Date:', ''],
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
                f.write("Operator Signature: _________________\n")
                f.write("Date: _________________\n")
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
        """Export report data to CSV format"""
        try:
            # This would extract the raw data from the report and format as CSV
            # Implementation depends on specific CSV format requirements
            csv_path = os.path.join(self.reports_dir, f"report_data_{report_id}.csv")
            
            # Placeholder implementation
            with open(csv_path, 'w') as f:
                f.write("timestamp,temperature,stage\n")
                # Add actual data export logic here
                
            return csv_path
            
        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            raise
