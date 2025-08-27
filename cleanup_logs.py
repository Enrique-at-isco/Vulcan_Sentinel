#!/usr/bin/env python3
"""
Log Cleanup Script for Vulcan Sentinel

Cleans up large log files and implements log rotation
"""

import os
import shutil
import logging
from datetime import datetime, timedelta
import glob

def cleanup_large_logs():
    """Clean up large log files"""
    print("=== Vulcan Sentinel Log Cleanup ===")
    
    log_dir = "logs"
    if not os.path.exists(log_dir):
        print("Logs directory not found. Creating...")
        os.makedirs(log_dir)
        return
    
    # Find all log files
    log_files = []
    for ext in ['*.log', '*.csv']:
        log_files.extend(glob.glob(os.path.join(log_dir, ext)))
    
    if not log_files:
        print("No log files found.")
        return
    
    print(f"Found {len(log_files)} log files:")
    
    total_size_before = 0
    files_to_cleanup = []
    
    for log_file in log_files:
        file_size = os.path.getsize(log_file)
        file_size_mb = round(file_size / (1024**2), 2)
        total_size_before += file_size
        
        print(f"  {os.path.basename(log_file)}: {file_size_mb} MB")
        
        # Flag files larger than 50MB for cleanup
        if file_size > 50 * 1024 * 1024:  # 50MB
            files_to_cleanup.append(log_file)
    
    print(f"\nTotal log size: {round(total_size_before / (1024**2), 2)} MB")
    
    if files_to_cleanup:
        print(f"\nFound {len(files_to_cleanup)} large files to clean up:")
        
        for file_path in files_to_cleanup:
            filename = os.path.basename(file_path)
            file_size_mb = round(os.path.getsize(file_path) / (1024**2), 2)
            
            # Create backup with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = file_path.replace('.log', f'_backup_{timestamp}.log')
            backup_path = backup_path.replace('.csv', f'_backup_{timestamp}.csv')
            
            print(f"  Backing up {filename} ({file_size_mb} MB) to {os.path.basename(backup_path)}")
            
            try:
                # Create backup
                shutil.copy2(file_path, backup_path)
                
                # Truncate original file to last 1000 lines
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                
                if len(lines) > 1000:
                    with open(file_path, 'w') as f:
                        f.writelines(lines[-1000:])
                    
                    new_size_mb = round(os.path.getsize(file_path) / (1024**2), 2)
                    print(f"    Truncated to {new_size_mb} MB (last 1000 lines)")
                else:
                    print(f"    File already small enough ({len(lines)} lines)")
                    
            except Exception as e:
                print(f"    Error processing {filename}: {e}")
    else:
        print("\nNo large files found that need cleanup.")
    
    # Clean up old backup files (older than 7 days)
    print("\nCleaning up old backup files...")
    cutoff_date = datetime.now() - timedelta(days=7)
    
    backup_files = glob.glob(os.path.join(log_dir, '*_backup_*.log'))
    backup_files.extend(glob.glob(os.path.join(log_dir, '*_backup_*.csv')))
    
    cleaned_count = 0
    for backup_file in backup_files:
        file_time = datetime.fromtimestamp(os.path.getmtime(backup_file))
        if file_time < cutoff_date:
            try:
                os.remove(backup_file)
                print(f"  Removed old backup: {os.path.basename(backup_file)}")
                cleaned_count += 1
            except Exception as e:
                print(f"  Error removing {os.path.basename(backup_file)}: {e}")
    
    if cleaned_count == 0:
        print("  No old backup files found.")
    
    # Final size check
    total_size_after = 0
    for log_file in glob.glob(os.path.join(log_dir, '*.log')):
        total_size_after += os.path.getsize(log_file)
    for log_file in glob.glob(os.path.join(log_dir, '*.csv')):
        total_size_after += os.path.getsize(log_file)
    
    print(f"\nLog cleanup complete!")
    print(f"Total log size before: {round(total_size_before / (1024**2), 2)} MB")
    print(f"Total log size after: {round(total_size_after / (1024**2), 2)} MB")
    print(f"Space saved: {round((total_size_before - total_size_after) / (1024**2), 2)} MB")

def setup_log_rotation():
    """Setup log rotation for future log files"""
    print("\n=== Setting up Log Rotation ===")
    
    # Create a simple log rotation configuration
    rotation_config = """
# Log rotation configuration for Vulcan Sentinel
# This file should be used with logrotate or similar tools

logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        # Restart services if needed
        # systemctl restart vulcan-sentinel
    endscript
}

logs/*.csv {
    weekly
    rotate 4
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
}
"""
    
    config_file = "logs/logrotate.conf"
    try:
        with open(config_file, 'w') as f:
            f.write(rotation_config)
        print(f"Log rotation configuration saved to {config_file}")
        print("To enable automatic log rotation, run:")
        print(f"  sudo logrotate -f {os.path.abspath(config_file)}")
    except Exception as e:
        print(f"Error creating log rotation config: {e}")

if __name__ == "__main__":
    cleanup_large_logs()
    setup_log_rotation()
