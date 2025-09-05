# =====================================================================================
# Target File: src/infrastructure/process_manager.py
# Source Reference: src/display_process_manager.py and process management from main.py
# =====================================================================================

import subprocess
import multiprocessing
import threading
import time
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, Future

from src.infrastructure.logging_handler import StructuredLogger
from src.config.settings import ProcessingConfig
from src.domain.errors import ProcessingError

class ProcessManager:
    """
    Manages process pools and subprocess execution for the application.
    
    FROM: Process management functionality from original `main.py` and 
          `display_process_manager.py`.
    REFACTORING NOTES: Centralizes all process management functionality.
    """
    
    def __init__(self, config: ProcessingConfig, logger: StructuredLogger):
        """
        Initialize process manager with configuration.
        
        Args:
            config: Processing configuration settings
            logger: Logger for recording operations
        """
        self.config = config
        self.logger = logger
        self._executor: Optional[ProcessPoolExecutor] = None
        self._active_processes: Dict[str, Future] = {}
        self._shutdown = False
    
    def start(self) -> None:
        """Start the process pool executor."""
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.config.max_workers
            )
            self.logger.info("Process manager started", {
                "max_workers": self.config.max_workers
            })
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the process manager and cleanup resources.
        
        Args:
            wait: Whether to wait for active processes to complete
        """
        self._shutdown = True
        
        if self._executor:
            self.logger.info("Shutting down process manager", {
                "active_processes": len(self._active_processes),
                "wait": wait
            })
            
            self._executor.shutdown(wait=wait)
            self._executor = None
            
            # Clear active processes
            self._active_processes.clear()
    
    def submit_case_processing(self, worker_func: Callable, case_id: str, 
                             case_path: Path, **kwargs) -> str:
        """
        Submit a case for processing in the worker pool.
        
        FROM: Process submission logic from original main.py.
        
        Args:
            worker_func: Worker function to execute
            case_id: Case identifier
            case_path: Path to case directory
            **kwargs: Additional arguments for worker function
            
        Returns:
            Process ID for tracking
        """
        if not self._executor:
            raise RuntimeError("Process manager not started")
        
        if self._shutdown:
            raise RuntimeError("Process manager is shutting down")
        
        self.logger.info("Submitting case for processing", {
            "case_id": case_id,
            "case_path": str(case_path)
        })
        
        # Submit to process pool
        future = self._executor.submit(
            worker_func, case_id, case_path, **kwargs
        )
        
        # Track the process
        process_id = f"case_{case_id}_{int(time.time())}"
        self._active_processes[process_id] = future
        
        # Add completion callback
        future.add_done_callback(
            lambda f: self._process_completed(process_id, f)
        )
        
        return process_id
    
    def _process_completed(self, process_id: str, future: Future) -> None:
        """Handle process completion and cleanup."""
        try:
            result = future.result()
            self.logger.info("Process completed successfully", {
                "process_id": process_id,
                "result": result
            })
        except Exception as e:
            self.logger.error("Process failed", {
                "process_id": process_id,
                "error": str(e)
            })
        finally:
            # Remove from active processes
            self._active_processes.pop(process_id, None)
    
    def get_active_process_count(self) -> int:
        """Get count of currently active processes."""
        return len(self._active_processes)
    
    def is_process_active(self, process_id: str) -> bool:
        """Check if a specific process is still active."""
        return process_id in self._active_processes
    
    def wait_for_process(self, process_id: str, timeout: Optional[float] = None) -> Any:
        """
        Wait for a specific process to complete.
        
        Args:
            process_id: Process identifier
            timeout: Maximum time to wait (None for indefinite)
            
        Returns:
            Process result
        """
        if process_id not in self._active_processes:
            raise ValueError(f"Process {process_id} not found")
        
        future = self._active_processes[process_id]
        return future.result(timeout=timeout)

class CommandExecutor:
    """
    Handles subprocess command execution with proper error handling and logging.
    
    FROM: Command execution patterns from various handler files in original codebase.
    REFACTORING NOTES: Centralizes command execution with consistent error handling.
    """
    
    def __init__(self, logger: StructuredLogger, default_timeout: int = 300):
        """
        Initialize command executor.
        
        Args:
            logger: Logger for recording operations
            default_timeout: Default timeout for commands in seconds
        """
        self.logger = logger
        self.default_timeout = default_timeout
    
    def execute_command(self, command: List[str], cwd: Optional[Path] = None, 
                       timeout: Optional[int] = None, capture_output: bool = True,
                       env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        """
        Execute a command with proper error handling and logging.
        
        FROM: Command execution patterns from original handler classes.
        
        Args:
            command: Command and arguments as list
            cwd: Working directory for command
            timeout: Command timeout (uses default if None)
            capture_output: Whether to capture stdout/stderr
            env: Environment variables
            
        Returns:
            CompletedProcess instance
        """
        timeout = timeout or self.default_timeout
        
        self.logger.debug("Executing command", {
            "command": ' '.join(command),
            "cwd": str(cwd) if cwd else None,
            "timeout": timeout
        })
        
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                timeout=timeout,
                capture_output=capture_output,
                text=True,
                env=env,
                check=True
            )
            
            self.logger.debug("Command completed successfully", {
                "command": command[0],
                "return_code": result.returncode,
                "stdout_length": len(result.stdout) if result.stdout else 0,
                "stderr_length": len(result.stderr) if result.stderr else 0
            })
            
            return result
            
        except subprocess.TimeoutExpired as e:
            self.logger.error("Command timed out", {
                "command": ' '.join(command),
                "timeout": timeout,
                "cwd": str(cwd) if cwd else None
            })
            raise ProcessingError(f"Command timed out after {timeout}s: {' '.join(command)}")
            
        except subprocess.CalledProcessError as e:
            self.logger.error("Command failed", {
                "command": ' '.join(command),
                "return_code": e.returncode,
                "stdout": e.stdout,
                "stderr": e.stderr,
                "cwd": str(cwd) if cwd else None
            })
            raise ProcessingError(f"Command failed with code {e.returncode}: {' '.join(command)}")
    
    def execute_command_async(self, command: List[str], cwd: Optional[Path] = None,
                            timeout: Optional[int] = None, 
                            env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """
        Execute a command asynchronously and return Popen object.
        
        Args:
            command: Command and arguments as list
            cwd: Working directory for command
            timeout: Command timeout (for documentation only)
            env: Environment variables
            
        Returns:
            Popen instance for the running process
        """
        self.logger.debug("Starting async command", {
            "command": ' '.join(command),
            "cwd": str(cwd) if cwd else None
        })
        
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )