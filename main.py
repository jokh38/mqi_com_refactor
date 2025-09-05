#!/usr/bin/env python3
# =====================================================================================
# Target File: main.py  
# Source Reference: src/main.py
# =====================================================================================

"""
Main entry point for the MQI Communicator application.

FROM: Refactored from original main.py, simplified to focus only on:
- File system event detection 
- Process pool management
- Application lifecycle (start/stop)

RESPONSIBILITY: 
- Watch for new case directories
- Manage worker process pool  
- Coordinate application startup/shutdown
- Handle top-level error recovery

The complex dependency injection logic has been moved to src/core/worker.py
"""

import sys
import signal
import time
import multiprocessing as mp
from pathlib import Path
from typing import Optional, NoReturn
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, DirCreatedEvent

from src.config.settings import Settings
from src.infrastructure.logging_handler import StructuredLogger  
from src.infrastructure.process_manager import ProcessManager
from src.ui.display import DisplayManager
from src.ui.provider import DashboardDataProvider
from src.database.connection import DatabaseConnection
from src.repositories.case_repo import CaseRepository
from src.repositories.gpu_repo import GpuRepository
from src.core.worker import worker_main


class CaseDetectionHandler(FileSystemEventHandler):
    """
    File system event handler for detecting new case directories.
    
    FROM: CaseDetectionHandler class from original main.py
    RESPONSIBILITY: Monitor directory creation events and queue new cases for processing.
    """
    
    def __init__(self, case_queue: mp.Queue, logger: StructuredLogger):
        """
        Initialize the case detection handler.
        
        Args:
            case_queue: Queue for communicating new cases to worker processes
            logger: Logger for recording events
        """
        super().__init__()
        self.case_queue = case_queue
        self.logger = logger
        
    def on_created(self, event) -> None:
        """
        Handle directory creation events.
        
        FROM: on_created method from original CaseDetectionHandler.
        
        Args:
            event: File system event from watchdog
        """
        if not event.is_directory:
            return
            
        case_path = Path(event.src_path)
        case_id = case_path.name
        
        self.logger.info(f"New case detected: {case_id} at {case_path}")
        
        try:
            # Add the case to the processing queue
            self.case_queue.put({
                'case_id': case_id,
                'case_path': str(case_path),
                'timestamp': time.time()
            })
            self.logger.info(f"Case {case_id} queued for processing")
            
        except Exception as e:
            self.logger.error(f"Failed to queue case {case_id}", {"error": str(e)})


class MQIApplication:
    """
    Main application controller.
    
    FROM: Main application logic from original main.py, but simplified.
    RESPONSIBILITY: Coordinate application lifecycle and component management.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the MQI application.
        
        Args:
            config_path: Path to configuration file
        """
        self.settings = Settings(config_path)
        self.logger: Optional[StructuredLogger] = None
        self.case_queue = mp.Queue()
        self.observer: Optional[Observer] = None
        self.executor: Optional[ProcessPoolExecutor] = None
        self.display_manager: Optional[DisplayManager] = None
        self.shutdown_event = threading.Event()
        
    def initialize_logging(self) -> None:
        """
        Initialize logging system.
        
        FROM: Logging initialization from original main.py.
        """
        try:
            self.logger = StructuredLogger(
                name="main",
                config=self.settings.logging
            )
            self.logger.info("MQI Communicator starting up")
        except Exception as e:
            print(f"Failed to initialize logging: {e}")
            sys.exit(1)
    
    def initialize_database(self) -> None:
        """
        Initialize database and ensure schema exists.
        
        FROM: Database initialization from original main.py.
        """
        try:
            db_path = self.settings.get_database_path()
            db_connection = DatabaseConnection(
                db_path=db_path,
                config=self.settings.database,
                logger=self.logger
            )
            
            # Initialize database schema
            db_connection.init_db()
            db_connection.close()
            
            self.logger.info(f"Database initialized at {db_path}")
            
        except Exception as e:
            self.logger.error("Failed to initialize database", {"error": str(e)})
            sys.exit(1)
    
    def start_file_watcher(self) -> None:
        """
        Start file system watcher for new cases.
        
        FROM: File watcher setup from original main.py.
        """
        try:
            case_dirs = self.settings.get_case_directories()
            scan_directory = case_dirs.get("scan")
            
            if not scan_directory or not scan_directory.exists():
                self.logger.error(f"Scan directory does not exist: {scan_directory}")
                return
                
            event_handler = CaseDetectionHandler(self.case_queue, self.logger)
            self.observer = Observer()
            self.observer.schedule(event_handler, str(scan_directory), recursive=False)
            self.observer.start()
            
            self.logger.info(f"Watching for new cases in: {scan_directory}")
            
        except Exception as e:
            self.logger.error("Failed to start file watcher", {"error": str(e)})
    
    def start_dashboard(self) -> None:
        """
        Start the dashboard UI if configured.
        
        FROM: Dashboard startup from original main.py.
        """
        try:
            if not self.settings.ui.auto_start:
                self.logger.info("Dashboard auto-start disabled")
                return
                
            # Create dashboard data provider
            db_path = self.settings.get_database_path()
            db_connection = DatabaseConnection(
                db_path=db_path,
                config=self.settings.database,
                logger=self.logger
            )
            
            case_repo = CaseRepository(db_connection, self.logger)
            gpu_repo = GpuRepository(db_connection, self.logger)
            provider = DashboardDataProvider(case_repo, gpu_repo, self.logger)
            
            # Start dashboard
            self.display_manager = DisplayManager(provider, self.logger)
            self.display_manager.start()
            
            self.logger.info("Dashboard started")
            
        except Exception as e:
            self.logger.error("Failed to start dashboard", {"error": str(e)})
    
    def run_worker_loop(self) -> None:
        """
        Main worker processing loop.
        
        FROM: Worker loop from original main.py, simplified.
        RESPONSIBILITY: Process queued cases using worker pool.
        """
        max_workers = self.settings.processing.max_workers
        
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            self.executor = executor
            self.logger.info(f"Started worker pool with {max_workers} processes")
            
            active_futures = {}
            
            while not self.shutdown_event.is_set():
                try:
                    # Check for new cases
                    try:
                        case_data = self.case_queue.get(timeout=1.0)
                        case_id = case_data['case_id']
                        case_path = Path(case_data['case_path'])
                        
                        self.logger.info(f"Processing case: {case_id}")
                        
                        # Submit case to worker - pass the entire settings object
                        future = executor.submit(
                            worker_main,
                            case_id,
                            case_path, 
                            self.settings
                        )
                        active_futures[future] = case_id
                        
                    except:
                        pass  # Queue timeout, continue
                    
                    # Check for completed workers
                    completed_futures = []
                    for future in as_completed(active_futures.keys(), timeout=0.1):
                        completed_futures.append(future)
                    
                    for future in completed_futures:
                        case_id = active_futures.pop(future)
                        try:
                            future.result()  # This will raise exception if worker failed
                            self.logger.info(f"Case {case_id} completed successfully")
                        except Exception as e:
                            self.logger.error(f"Case {case_id} failed", {"error": str(e)})
                    
                except KeyboardInterrupt:
                    self.logger.info("Received shutdown signal")
                    break
                except Exception as e:
                    self.logger.error("Error in worker loop", {"error": str(e)})
                    time.sleep(1)  # Brief pause before retrying
    
    def shutdown(self) -> None:
        """
        Graceful shutdown of all components.
        
        FROM: Shutdown logic from original main.py.
        """
        self.logger.info("Shutting down MQI Communicator")
        self.shutdown_event.set()
        
        # Stop file watcher
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
        # Stop dashboard
        if self.display_manager:
            self.display_manager.stop()
            
        # Executor shutdown handled by context manager
        
        self.logger.info("Shutdown complete")
    
    def run(self) -> NoReturn:
        """
        Main application entry point.
        
        FROM: main() function from original main.py, refactored.
        """
        try:
            # Initialize core components
            self.initialize_logging()
            self.initialize_database()
            
            # Start monitoring and UI
            self.start_file_watcher()
            self.start_dashboard()
            
            # Run main processing loop
            self.run_worker_loop()
            
        except KeyboardInterrupt:
            pass
        except Exception as e:
            if self.logger:
                self.logger.error("Application failed", {"error": str(e)})
            else:
                print(f"Application failed: {e}")
        finally:
            self.shutdown()


def setup_signal_handlers(app: MQIApplication) -> None:
    """
    Setup signal handlers for graceful shutdown.
    
    FROM: Signal handling from original main.py.
    """
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        app.shutdown()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> NoReturn:
    """
    Application entry point.
    
    FROM: Main entry point from original main.py, simplified.
    
    Usage:
        python main.py [config_file]
    """
    # Determine config file path
    config_path = None
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        # Default config location
        default_config = Path("config/config.yaml")
        if default_config.exists():
            config_path = default_config
    
    # Create and run application
    app = MQIApplication(config_path)
    setup_signal_handlers(app)
    app.run()


if __name__ == "__main__":
    main()