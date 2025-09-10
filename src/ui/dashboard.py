#!/usr/bin/env python3
# =====================================================================================
# Target File: src/ui/dashboard.py
# Purpose: UI Process Entry Point - Serves as the entry point for the UI process
# =====================================================================================

"""UI Process Entry Point for the MQI Communicator Dashboard.

This script initializes all necessary components and starts the display
manager in its own process space.
"""

import sys
import signal
import time
from pathlib import Path
from typing import NoReturn

from src.config.settings import Settings
from src.infrastructure.logging_handler import StructuredLogger
from src.database.connection import DatabaseConnection
from src.repositories.case_repo import CaseRepository
from src.repositories.gpu_repo import GpuRepository
from src.ui.provider import DashboardDataProvider
from src.ui.display import DisplayManager


class DashboardProcess:
    """Main dashboard process controller.

    This class is responsible for initializing and managing the UI components
    in a separate process.
    """
    
    def __init__(self, database_path: str):
        """Initialize the dashboard process.

        Args:
            database_path (str): The path to the SQLite database file.
        """
        self.database_path = database_path
        self.logger: StructuredLogger = None
        self.display_manager: DisplayManager = None
        self.running = False
        
    def initialize_logging(self) -> None:
        """Initialize logging for the UI process."""
        try:
            # Use default settings for UI process logging
            settings = Settings()
            self.logger = StructuredLogger(
                name="ui_dashboard",
                config=settings.logging
            )
            self.logger.info("Dashboard process starting", {
                "database_path": self.database_path
            })
        except Exception as e:
            print(f"Failed to initialize logging: {e}")
            sys.exit(1)
    
    def setup_database_components(self) -> tuple[CaseRepository, GpuRepository]:
        """Setup the database connection and repositories.

        Returns:
            tuple[CaseRepository, GpuRepository]: A tuple containing the case and GPU repositories.
        """
        try:
            # Use default settings for database connection
            settings = Settings()
            db_connection = DatabaseConnection(
                db_path=Path(self.database_path),
                config=settings.database,
                logger=self.logger
            )
            
            # Create repositories
            case_repo = CaseRepository(db_connection, self.logger)
            gpu_repo = GpuRepository(db_connection, self.logger)
            
            self.logger.info("Database components initialized successfully")
            return case_repo, gpu_repo
            
        except Exception as e:
            self.logger.error("Failed to setup database components", {"error": str(e)})
            sys.exit(1)
    
    def start_display(self) -> None:
        """Start the display manager."""
        try:
            # Setup database components
            case_repo, gpu_repo = self.setup_database_components()
            
            # Create data provider
            provider = DashboardDataProvider(case_repo, gpu_repo, self.logger)
            
            # Create and start display manager
            self.display_manager = DisplayManager(provider, self.logger)
            self.display_manager.start()
            
            self.running = True
            self.logger.info("Dashboard display started successfully")
            
        except Exception as e:
            self.logger.error("Failed to start display", {"error": str(e)})
            sys.exit(1)
    
    def stop_display(self) -> None:
        """Stop the display manager."""
        if self.display_manager and self.running:
            self.logger.info("Stopping dashboard display")
            self.display_manager.stop()
            self.running = False
            self.logger.info("Dashboard display stopped")
    
    def run(self) -> NoReturn:
        """The main run loop for the dashboard process."""
        try:
            # Initialize components
            self.initialize_logging()
            self.start_display()
            
            # Keep the process alive
            while self.running:
                time.sleep(1)
                
                # Check if display manager is still running
                if not self.display_manager or not self.display_manager.running:
                    self.logger.warning("Display manager stopped unexpectedly")
                    break
                    
        except KeyboardInterrupt:
            self.logger.info("Dashboard process received interrupt signal")
        except Exception as e:
            if self.logger:
                self.logger.error("Dashboard process failed", {"error": str(e)})
            else:
                print(f"Dashboard process failed: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            self.stop_display()
            if self.logger:
                self.logger.info("Dashboard process cleanup complete")
        except Exception as e:
            print(f"Error during cleanup: {e}")


def setup_signal_handlers(dashboard: DashboardProcess) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        dashboard (DashboardProcess): The DashboardProcess instance to shut down.
    """
    def signal_handler(signum, frame):
        print(f"\\nReceived signal {signum}, shutting down dashboard...")
        dashboard.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> NoReturn:
    """The main entry point for the dashboard process."""
    if len(sys.argv) != 2:
        print("Usage: python -m src.ui.dashboard <database_path>")
        sys.exit(1)
    
    database_path = sys.argv[1]
    
    # Validate database path
    if not Path(database_path).exists():
        print(f"Database file does not exist: {database_path}")
        sys.exit(1)
    
    # Create and run dashboard
    dashboard = DashboardProcess(database_path)
    setup_signal_handlers(dashboard)
    
    print(f"Starting MQI Dashboard UI (PID: {sys.argv[0]})...")
    print(f"Database: {database_path}")
    print("Press Ctrl+C to stop")
    
    dashboard.run()


if __name__ == "__main__":
    main()