# =====================================================================================
# Target File: src/infrastructure/process_manager.py
# Source Reference: src/display_process_manager.py and process management from main.py
# =====================================================================================
"""!
@file process_manager.py
@brief Manages process pools and subprocess execution for the application.
"""

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
    """!
    @brief Manages process pools and subprocess execution for the application.
    """
    
    def __init__(self, config: ProcessingConfig, logger: StructuredLogger):
        """!
        @brief Initialize the process manager with configuration.
        @param config: The processing configuration settings.
        @param logger: The logger for recording operations.
        """
        self.config = config
        self.logger = logger
        self._executor: Optional[ProcessPoolExecutor] = None
        self._active_processes: Dict[str, Future] = {}
        self._shutdown = False
    
    def start(self) -> None:
        """!
        @brief Start the process pool executor.
        """
        if self._executor is None:
            self._executor = ProcessPoolExecutor(
                max_workers=self.config.max_workers
            )
            self.logger.info("Process manager started", {
                "max_workers": self.config.max_workers
            })
    
    def shutdown(self, wait: bool = True) -> None:
        """!
        @brief Shutdown the process manager and clean up resources.
        @param wait: Whether to wait for active processes to complete.
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
        """!
        @brief Submit a case for processing in the worker pool.
        @param worker_func: The worker function to execute.
        @param case_id: The case identifier.
        @param case_path: The path to the case directory.
        @param **kwargs: Additional arguments for the worker function.
        @return A process ID for tracking.
        @raises RuntimeError: If the process manager is not started or is shutting down.
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
        """!
        @brief Handle process completion and cleanup.
        @param process_id: The ID of the completed process.
        @param future: The Future object representing the completed process.
        """
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
        """!
        @brief Get the count of currently active processes.
        @return The number of active processes.
        """
        return len(self._active_processes)
    
    def is_process_active(self, process_id: str) -> bool:
        """!
        @brief Check if a specific process is still active.
        @param process_id: The ID of the process to check.
        @return True if the process is active, False otherwise.
        """
        return process_id in self._active_processes
    
    def wait_for_process(self, process_id: str, timeout: Optional[float] = None) -> Any:
        """!
        @brief Wait for a specific process to complete.
        @param process_id: The process identifier.
        @param timeout: The maximum time to wait (None for indefinite).
        @return The result of the process.
        @raises ValueError: If the process ID is not found.
        """
        if process_id not in self._active_processes:
            raise ValueError(f"Process {process_id} not found")
        
        future = self._active_processes[process_id]
        return future.result(timeout=timeout)

class CommandExecutor:
    """!
    @brief Handles subprocess command execution with proper error handling and logging.
    """
    
    def __init__(self, logger: StructuredLogger, default_timeout: int = 300):
        """!
        @brief Initialize the command executor.
        @param logger: The logger for recording operations.
        @param default_timeout: The default timeout for commands in seconds.
        """
        self.logger = logger
        self.default_timeout = default_timeout
    
    def execute_command(self, command: List[str], cwd: Optional[Path] = None, 
                       timeout: Optional[int] = None, capture_output: bool = True,
                       env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        """!
        @brief Execute a command with proper error handling and logging.
        @param command: The command and arguments as a list.
        @param cwd: The working directory for the command.
        @param timeout: The command timeout (uses default if None).
        @param capture_output: Whether to capture stdout/stderr.
        @param env: Environment variables.
        @return A subprocess.CompletedProcess instance.
        @raises ProcessingError: If the command fails or times out.
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
        """!
        @brief Execute a command asynchronously and return a Popen object.
        @param command: The command and arguments as a list.
        @param cwd: The working directory for the command.
        @param timeout: The command timeout (for documentation only).
        @param env: Environment variables.
        @return A subprocess.Popen instance for the running process.
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