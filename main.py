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
from src.infrastructure.ui_process_manager import UIProcessManager
from src.database.connection import DatabaseConnection
from src.repositories.gpu_repo import GpuRepository
from src.repositories.case_repo import CaseRepository
from src.infrastructure.gpu_monitor import GpuMonitor
from src.handlers.remote_handler import RemoteHandler
from src.utils.retry_policy import RetryPolicy
from src.core.worker import worker_main
from src.core.dispatcher import prepare_beam_jobs


def scan_existing_cases(case_queue: mp.Queue, settings: Settings, logger: StructuredLogger) -> None:
    """
    Scan the scan_directory at startup for existing cases and add any missing ones to the processing queue.
    
    This function compares case directories found in the file system with those already recorded
    in the database and queues any new cases for processing.
    
    Args:
        case_queue: Queue for communicating new cases to worker processes
        settings: Application settings containing directory paths
        logger: Logger for recording operations
    """
    try:
        # Get scan directory from settings
        case_dirs = settings.get_case_directories()
        scan_directory = case_dirs.get("scan")
        
        if not scan_directory or not scan_directory.exists():
            logger.warning(f"Scan directory does not exist or is not configured: {scan_directory}")
            return
        
        # Initialize database connection and case repository
        db_path = settings.get_database_path()
        db_connection = DatabaseConnection(
            db_path=db_path,
            config=settings.database,
            logger=logger
        )
        case_repo = CaseRepository(db_connection, logger)
        
        try:
            # Get all case IDs from database
            existing_case_ids = set(case_repo.get_all_case_ids())
            logger.info(f"Found {len(existing_case_ids)} cases already in database")
            
            # Scan file system for case directories
            filesystem_cases = []
            for item in scan_directory.iterdir():
                if item.is_dir():
                    case_id = item.name
                    filesystem_cases.append((case_id, item))
            
            logger.info(f"Found {len(filesystem_cases)} case directories in scan directory")
            
            # Find cases that are in file system but not in database
            new_cases = []
            for case_id, case_path in filesystem_cases:
                if case_id not in existing_case_ids:
                    new_cases.append((case_id, case_path))
            
            # Add new cases to processing queue
            if new_cases:
                logger.info(f"Found {len(new_cases)} new cases to process")
                for case_id, case_path in new_cases:
                    try:
                        case_queue.put({
                            'case_id': case_id,
                            'case_path': str(case_path),
                            'timestamp': time.time()
                        })
                        logger.info(f"Queued existing case for processing: {case_id}")
                    except Exception as e:
                        logger.error(f"Failed to queue existing case {case_id}", {"error": str(e)})
            else:
                logger.info("No new cases found during startup scan")
                
        finally:
            db_connection.close()
            
    except Exception as e:
        logger.error("Failed to scan existing cases during startup", {"error": str(e)})


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
        self.ui_process_manager: Optional[UIProcessManager] = None
        self.gpu_monitor: Optional[GpuMonitor] = None
        self.monitor_db_connection: Optional[DatabaseConnection] = None
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
        Start the dashboard UI as a separate process if configured.
        
        FROM: Dashboard startup from original main.py, modified to use UIProcessManager.
        """
        try:
            if not self.settings.ui.auto_start:
                self.logger.info("Dashboard auto-start disabled")
                return
                
            # Get database path
            db_path = self.settings.get_database_path()
            
            # Create UI process manager
            self.ui_process_manager = UIProcessManager(
                database_path=str(db_path),
                config=self.settings,
                logger=self.logger
            )
            
            # Start UI as separate process
            if self.ui_process_manager.start():
                self.logger.info("Dashboard UI process started successfully")
            else:
                self.logger.error("Failed to start dashboard UI process")
            
        except Exception as e:
            self.logger.error("Failed to start dashboard", {"error": str(e)})
    
    def start_gpu_monitor(self) -> None:
        """
        Start the GPU monitoring service as a background thread.
        """
        try:
            self.logger.info("Initializing GPU monitoring service.")

            # Create a dedicated database connection for the monitor
            db_path = self.settings.get_database_path()
            self.monitor_db_connection = DatabaseConnection(
                db_path=db_path,
                config=self.settings.database,
                logger=self.logger
            )
            gpu_repo = GpuRepository(self.monitor_db_connection, self.logger)

            # Create dependencies for RemoteHandler
            retry_policy = RetryPolicy(
                max_attempts=self.settings.retry_policy.max_retries,
                base_delay=self.settings.retry_policy.initial_delay_seconds,
                max_delay=self.settings.retry_policy.max_delay_seconds,
                backoff_multiplier=self.settings.retry_policy.backoff_multiplier,
                logger=self.logger
            )
            remote_handler = RemoteHandler(self.settings, self.logger, retry_policy)

            # Get command and interval from settings
            command_str = self.settings.gpu.gpu_monitor_command
            command_list = command_str.split()
            interval = self.settings.gpu.monitor_interval

            self.gpu_monitor = GpuMonitor(
                logger=self.logger,
                remote_handler=remote_handler,
                gpu_repository=gpu_repo,
                command=command_list,
                update_interval=interval
            )

            self.gpu_monitor.start()
            self.logger.info("GPU monitoring service started.")

        except Exception as e:
            self.logger.error("Failed to start GPU monitor", {"error": str(e)})

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
                        case_id = case_data["case_id"]
                        case_path = Path(case_data["case_path"])

                        self.logger.info(f"Dispatching case: {case_id}")

                        # Get the list of beam jobs to run
                        beam_jobs = prepare_beam_jobs(case_id, case_path, self.settings)

                        # Submit a worker for each beam
                        for job in beam_jobs:
                            beam_id = job["beam_id"]
                            beam_path = job["beam_path"]
                            self.logger.info(f"Submitting beam worker for: {beam_id}")
                            future = executor.submit(
                                worker_main,
                                beam_id=beam_id,
                                beam_path=beam_path,
                                settings=self.settings
                            )
                            # The active_futures now tracks beams, not cases.
                            active_futures[future] = beam_id

                    except:
                        pass  # Queue timeout, continue

                    # Check for completed workers
                    completed_futures = []
                    for future in as_completed(active_futures.keys(), timeout=0.1):
                        completed_futures.append(future)

                    for future in completed_futures:
                        beam_id = active_futures.pop(future)
                        try:
                            # future.exception()을 통해 예외 발생 여부를 명시적으로 확인
                            if future.exception() is not None:
                                # 예외가 있다면 future.result()를 호출하여 예외를 발생시키고 catch 블록에서 처리
                                future.result()
                            else:
                                self.logger.info(
                                    f"Beam worker {beam_id} completed successfully"
                                )
                        except Exception as e:
                            self.logger.error(
                                f"Beam worker {beam_id} failed", {"error": str(e)}
                            )
                    
                except KeyboardInterrupt:
                    self.logger.info("Received shutdown signal")
                    break
                except Exception as e:
                    self.logger.error("Error in worker loop", {"error": str(e)})
                
                # Prevent busy-waiting
                time.sleep(1)
    
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
            
        # Stop GPU monitor
        if self.gpu_monitor:
            self.logger.info("Stopping GPU monitor.")
            self.gpu_monitor.stop()

        if self.monitor_db_connection:
            self.monitor_db_connection.close()
            
        # Stop dashboard UI process
        if self.ui_process_manager:
            self.ui_process_manager.stop()
            
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
            
            # Scan for existing cases that haven't been processed yet
            self.logger.info("Scanning for existing cases at startup")
            scan_existing_cases(self.case_queue, self.settings, self.logger)
            
            # Start monitoring and UI
            self.start_file_watcher()
            self.start_dashboard()
            self.start_gpu_monitor()
            
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
        # Using print() here can corrupt the rich display during shutdown.
        # It's better to use the logger if it's available.
        message = f"\nReceived signal {signum}, shutting down..."
        if app.logger:
            app.logger.info(message.strip())
        else:
            print(message)
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