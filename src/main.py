"""
Main entry point for the Industrial Data Logger application

This module coordinates all services including:
- Modbus polling
- Database management
- API server
- Printer service
- Report generation
"""

import os
import sys
import signal
import logging
import threading
from datetime import datetime
from typing import Dict, Any

# Add the src directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modbus_poller import ModbusPoller
from src.database import DatabaseManager
from src.config_manager import ConfigManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DataLoggerApp:
    """Main application class that coordinates all services"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.db_manager = DatabaseManager()
        self.modbus_poller = None
        self.running = False
        self.services = {}
        
        # Load configuration
        self.config = self.config_manager.load_config()
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.shutdown()
    
    def initialize(self):
        """Initialize all application components"""
        try:
            logger.info("Initializing Industrial Data Logger...")
            
            # Create necessary directories
            os.makedirs('logs', exist_ok=True)
            os.makedirs('reports', exist_ok=True)
            os.makedirs('data', exist_ok=True)
            
            # Initialize database
            logger.info("Initializing database...")
            self.db_manager.create_tables()
            
            # Initialize Modbus poller
            logger.info("Initializing Modbus poller...")
            self.modbus_poller = ModbusPoller()
            
            # Log initialization event
            self.db_manager.log_event(
                event_type="SYSTEM_STARTUP",
                message="Industrial Data Logger initialized successfully",
                severity="INFO"
            )
            
            logger.info("Initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize application: {e}")
            return False
    
    def start(self):
        """Start all application services"""
        try:
            if not self.initialize():
                logger.error("Failed to initialize application")
                return False
            
            logger.info("Starting Industrial Data Logger services...")
            self.running = True
            
            # Start Modbus poller
            if self.modbus_poller:
                logger.info("Starting Modbus poller...")
                self.modbus_poller.start()
                self.services['modbus_poller'] = self.modbus_poller
            
            # Log startup event
            self.db_manager.log_event(
                event_type="SERVICES_STARTED",
                message="All services started successfully",
                severity="INFO"
            )
            
            logger.info("All services started successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start services: {e}")
            return False
    
    def stop(self):
        """Stop all application services"""
        try:
            logger.info("Stopping Industrial Data Logger services...")
            self.running = False
            
            # Stop Modbus poller
            if self.modbus_poller:
                logger.info("Stopping Modbus poller...")
                self.modbus_poller.stop()
            
            # Log shutdown event
            self.db_manager.log_event(
                event_type="SERVICES_STOPPED",
                message="All services stopped",
                severity="INFO"
            )
            
            logger.info("All services stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping services: {e}")
    
    def shutdown(self):
        """Graceful shutdown of the application"""
        logger.info("Shutting down Industrial Data Logger...")
        
        # Stop all services
        self.stop()
        
        # Close database connection
        if self.db_manager:
            self.db_manager.close()
        
        logger.info("Shutdown completed")
        sys.exit(0)
    
    def get_status(self) -> Dict[str, Any]:
        """Get application status"""
        status = {
            'running': self.running,
            'timestamp': datetime.now().isoformat(),
            'version': self.config.get('version', '1.0.0'),
            'services': {}
        }
        
        # Get Modbus poller status
        if self.modbus_poller:
            status['services']['modbus_poller'] = self.modbus_poller.get_status()
        
        # Get database info
        if self.db_manager:
            status['database'] = self.db_manager.get_database_info()
        
        return status
    
    def run(self):
        """Main application loop"""
        try:
            if not self.start():
                logger.error("Failed to start application")
                return False
            
            logger.info("Industrial Data Logger is running. Press Ctrl+C to stop.")
            
            # Main loop - keep the application running
            while self.running:
                try:
                    # Sleep for a short interval
                    import time
                    time.sleep(1)
                    
                    # Check if any services have failed
                    if self.modbus_poller and not self.modbus_poller.running:
                        logger.error("Modbus poller has stopped unexpectedly")
                        break
                        
                except KeyboardInterrupt:
                    logger.info("Received keyboard interrupt")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    break
            
            return True
            
        except Exception as e:
            logger.error(f"Fatal error in application: {e}")
            return False
        finally:
            self.shutdown()


def main():
    """Main entry point"""
    try:
        # Create and run the application
        app = DataLoggerApp()
        success = app.run()
        
        if success:
            logger.info("Application completed successfully")
        else:
            logger.error("Application failed")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 