// Chart configuration
const chartColors = {
    preheat: 'rgba(255, 99, 132, 1)',
    main_heat: 'rgba(54, 162, 235, 1)',
    rib_heat: 'rgba(75, 192, 192, 1)'
};

const chartBorderColors = {
    preheat: 'rgba(255, 99, 132, 0.8)',
    main_heat: 'rgba(54, 162, 235, 0.8)',
    rib_heat: 'rgba(75, 192, 192, 0.8)'
};

// Initialize chart
let temperatureChart;

document.addEventListener('DOMContentLoaded', function() {
    const ctx = document.getElementById('temperatureChart').getContext('2d');
    temperatureChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Preheat',
                    data: [],
                    borderColor: chartColors.preheat,
                    backgroundColor: chartBorderColors.preheat,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                },
                {
                    label: 'Main Heat',
                    data: [],
                    borderColor: chartColors.main_heat,
                    backgroundColor: chartBorderColors.main_heat,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                },
                {
                    label: 'Rib Heat',
                    data: [],
                    borderColor: chartColors.rib_heat,
                    backgroundColor: chartBorderColors.rib_heat,
                    borderWidth: 2,
                    fill: false,
                    tension: 0.1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: 'Temperature Readings Over Time'
                },
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        unit: 'hour',
                        displayFormats: {
                            hour: 'MMM dd, HH:mm'
                        }
                    },
                    title: {
                        display: true,
                        text: 'Time'
                    }
                },
                y: {
                    title: {
                        display: true,
                        text: 'Temperature (°F)'
                    },
                    beginAtZero: false
                }
            },
            interaction: {
                intersect: false,
                mode: 'index'
            }
        }
    });

    // Load initial data
    updateChartData();
    updateStorageInfo();

    // Set up auto-refresh intervals
    setInterval(updateChartData, 30000); // Every 30 seconds
    setInterval(updateStorageInfo, 120000); // Every 2 minutes

    // Auto-refresh page every 5 minutes
    setTimeout(function() {
        location.reload();
    }, 300000);
});

// Function to update chart data
async function updateChartData() {
    try {
        const response = await fetch('/api/readings/history?days=1');
        const data = await response.json();
        
        // Clear existing data
        temperatureChart.data.labels = [];
        temperatureChart.data.datasets.forEach(dataset => {
            dataset.data = [];
        });
        
        // Process data for each device
        const deviceData = {
            preheat: [],
            main_heat: [],
            rib_heat: []
        };
        
        // Collect data points
        Object.keys(data).forEach(deviceName => {
            if (data[deviceName] && Array.isArray(data[deviceName])) {
                data[deviceName].forEach(reading => {
                    const timestamp = new Date(reading.timestamp);
                    const temp = reading.temperature;
                    
                    if (deviceName === 'preheat') {
                        deviceData.preheat.push({x: timestamp, y: temp});
                    } else if (deviceName === 'main_heat') {
                        deviceData.main_heat.push({x: timestamp, y: temp});
                    } else if (deviceName === 'rib_heat') {
                        deviceData.rib_heat.push({x: timestamp, y: temp});
                    }
                });
            }
        });
        
        // Sort data by timestamp
        Object.keys(deviceData).forEach(device => {
            deviceData[device].sort((a, b) => a.x - b.x);
        });
        
        // Update chart datasets
        temperatureChart.data.datasets[0].data = deviceData.preheat;
        temperatureChart.data.datasets[1].data = deviceData.main_heat;
        temperatureChart.data.datasets[2].data = deviceData.rib_heat;
        
        temperatureChart.update();
        
    } catch (error) {
        console.error('Error updating chart data:', error);
    }
}

// Function to format bytes to human readable format
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Function to update storage information
async function updateStorageInfo() {
    try {
        const response = await fetch('/api/storage-info');
        const data = await response.json();
        
        // Update system storage
        const systemStorage = document.getElementById('system-storage');
        const systemUsagePercent = (data.system_storage.used / data.system_storage.total) * 100;
        const systemBarClass = systemUsagePercent > 80 ? 'danger' : systemUsagePercent > 60 ? 'warning' : '';
        
        systemStorage.innerHTML = `
            <div class="storage-info">
                <div>Total: ${formatBytes(data.system_storage.total)}</div>
                <div>Used: ${formatBytes(data.system_storage.used)}</div>
                <div>Available: ${formatBytes(data.system_storage.available)}</div>
                <div class="storage-bar">
                    <div class="storage-bar-fill ${systemBarClass}" style="width: ${systemUsagePercent}%"></div>
                </div>
                <div>${systemUsagePercent.toFixed(1)}% used</div>
            </div>
        `;
        
        // Update database size
        const databaseSize = document.getElementById('database-size');
        databaseSize.innerHTML = `
            <div class="storage-info">
                <div>Database: ${formatBytes(data.database_size)}</div>
                <div>Records: ${data.record_count.toLocaleString()}</div>
                <div>Oldest: ${data.oldest_record}</div>
                <div>Newest: ${data.newest_record}</div>
            </div>
        `;
        
        // Update data consumption
        const dataConsumption = document.getElementById('data-consumption');
        dataConsumption.innerHTML = `
            <div class="storage-info">
                <div>Today: ${formatBytes(data.daily_consumption)}</div>
                <div>This Week: ${formatBytes(data.weekly_consumption)}</div>
                <div>This Month: ${formatBytes(data.monthly_consumption)}</div>
                <div>Avg/Day: ${formatBytes(data.avg_daily_consumption)}</div>
            </div>
        `;
        
    } catch (error) {
        console.error('Error updating storage info:', error);
    }
}

// Function to cleanup duplicate readings
async function cleanupDuplicates() {
    if (confirm('Are you sure you want to clean up duplicate readings? This cannot be undone.')) {
        try {
            const response = await fetch('/api/cleanup-duplicates');
            const result = await response.json();
            
            if (result.success) {
                alert(`Success: ${result.message}`);
                location.reload();
            } else {
                alert(`Error: ${result.error}`);
            }
        } catch (error) {
            console.error('Error cleaning up duplicates:', error);
            alert('Error cleaning up duplicates');
        }
    }
} 