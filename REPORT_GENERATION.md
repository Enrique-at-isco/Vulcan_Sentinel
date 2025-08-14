# Report Generation System

The Vulcan Sentinel system includes a comprehensive report generation feature that creates detailed work order reports in multiple formats.

## Features

### Report Types
1. **PDF Reports** - Full-featured reports with charts, tables, and professional formatting
2. **Thermal Receipts** - Compact reports suitable for thermal printers
3. **CSV Export** - Raw data export for further analysis

### Report Content

#### Header Information
- Work Order Number (unique identifier)
- Date & Time (start/end timestamps)
- Machine/Line ID (equipment identifier)

#### Process Summary
- Run Duration (total active production time)
- Temperature Time Series Plot (all three sensors)

#### Key Process Data
- **Temperature Data Table**
  - Average, minimum, and maximum temperatures
  - Duration for each heat stage
  - Data for Preheat, Main Heat, and Rib Heat sensors

- **Temperature Setpoints & Deviations**
  - Set temperature for each controller
  - +/- deviation tolerances
  - Data for all three heat stages

- **Trigger Events**
  - Timestamps of critical process points
  - Stage transitions (start/end of each heat)
  - Temperature target achievements
  - Heat up/cool down events

#### Manual Overrides
- Logged cases where set temperatures were manually changed
- Timestamp and sensor information
- Action descriptions

#### Footer
- Operator signature line (for printed copies)
- Digital Report ID (sequential numbering for authenticity)
- Generation timestamp

## Usage

### Web Interface

1. Navigate to `/reports` in your web browser
2. Fill out the report generation form:
   - Work Order Number
   - Start Time
   - End Time
   - Machine/Line ID
   - Output Format (PDF or Thermal)
3. Click "Generate Report"
4. Download the generated report

### API Endpoints

#### Generate Report
```http
POST /api/reports/generate
Content-Type: application/json

{
    "work_order_number": "WO-12345",
    "start_time": "2025-01-15T08:00:00",
    "end_time": "2025-01-15T09:00:00",
    "machine_id": "Line-07",
    "output_format": "pdf"
}
```

#### Get Report History
```http
GET /api/reports/history?limit=50
```

#### Download Report
```http
GET /api/reports/download/{report_id}
```

#### Export CSV
```http
GET /api/reports/csv/{report_id}
```

### Command Line Testing

Run the test script to generate sample reports:

```bash
cd Vulcan_Sentinel
python test_report_generation.py
```

This will:
1. Generate sample temperature data
2. Create both PDF and thermal reports
3. Test CSV export functionality
4. Display report history

## File Structure

```
Vulcan_Sentinel/
├── src/
│   ├── report_generator.py    # Main report generation logic
│   ├── web_server.py          # Web interface with report endpoints
│   └── templates/
│       └── reports.html       # Report generation web interface
├── reports/                   # Generated reports storage
│   ├── work_order_report_*.pdf
│   ├── thermal_report_*.txt
│   ├── report_metadata.json   # Report history
│   └── report_counter.json    # Sequential ID counter
├── test_report_generation.py  # Test script
└── requirements.txt           # Dependencies
```

## Dependencies

The report generation system requires these additional packages:

```
matplotlib==3.7.2      # For temperature plots
reportlab==4.0.4       # For PDF generation
numpy==1.24.3          # For data processing
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### Temperature Setpoints

Default setpoints are configured in the `ReportGenerator` class:

```python
setpoints = {
    'preheat': {'set_temp': 300, 'deviation': 5},
    'main_heat': {'set_temp': 400, 'deviation': 5},
    'rib_heat': {'set_temp': 350, 'deviation': 5}
}
```

### Report Storage

Reports are stored in the `reports/` directory:
- PDF files: `work_order_report_{ID}.pdf`
- Thermal files: `thermal_report_{ID}.txt`
- CSV exports: `report_data_{ID}.csv`

### Digital Signatures

Each report includes a digital signature (SHA-256 hash) for authenticity verification.

## Customization

### Adding New Report Sections

To add new sections to reports, modify the `_create_report_content` method in `ReportGenerator`.

### Custom Plot Styling

Modify the `_generate_temperature_plot` method to customize chart appearance.

### Report Templates

PDF reports use ReportLab templates. Modify the `_generate_pdf_report` method for layout changes.

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   - Ensure all required packages are installed
   - Check `requirements.txt` for correct versions

2. **No Data Available**
   - Verify that temperature data exists for the specified time range
   - Check database connectivity

3. **Plot Generation Fails**
   - Ensure matplotlib backend is properly configured
   - Check file permissions for report directory

4. **PDF Generation Errors**
   - Verify ReportLab installation
   - Check for sufficient disk space

### Logging

Report generation activities are logged with the `report_generator` logger. Check logs for detailed error information.

## Integration

The report generator integrates with:
- **Database Manager** - For data retrieval
- **Config Manager** - For device configuration
- **Web Server** - For API endpoints and web interface
- **Main Application** - For system initialization

## Future Enhancements

Potential improvements:
- Email report delivery
- Scheduled report generation
- Custom report templates
- Advanced charting options
- Report archiving and compression
- Multi-language support
