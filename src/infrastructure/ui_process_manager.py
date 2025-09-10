# =====================================================================================
# Target File: src/infrastructure/ui_process_manager.py
# Source Reference: jsons/display_process_manager.json
# =====================================================================================
"""Manages the UI subprocess lifecycle, handling its creation, monitoring, and termination."""

import subprocess
import sys
import platform
import time
from typing import Optional, Dict, Any, IO
from pathlib import Path

from src.infrastructure.logging_handler import StructuredLogger
from src.config.settings import Settings


class UIProcessManager:
    """A professional manager for the UI subprocess lifecycle, handling its creation,
    monitoring, and clean termination with separate console window support.

    This class is responsible for launching and managing the UI as a separate process
    with proper console window handling on Windows systems.
    """
    
    def __init__(self, 
                 database_path: str, 
                 config_path: Optional[Path], 
                 config: Settings, 
                 logger: StructuredLogger):
        """Initializes the UIProcessManager.

        Args:
            database_path (str): The resolved path to the SQLite database file.
            config (Settings): The application configuration object.
            logger (StructuredLogger): A logger instance for status messages.
        """
        self.database_path = database_path
        self.config_path = config_path
        self.config = config
        self.logger = logger
        self.project_root = Path(__file__).parent.parent.parent
        self._process: Optional[subprocess.Popen] = None
        self._stdout_log_file: Optional[IO[str]] = None
        self._stderr_log_file: Optional[IO[str]] = None
        self._is_running = False
        self.log_dir = self.project_root / self.config.logging.log_dir
    
    def start(self) -> bool:
        """Starts the UI as an independent process.

        Creates a new console window on Windows systems as per original behavior.

        Returns:
            bool: True if the process started successfully, False otherwise.
        """
        if self._is_running:
            if self.logger:
                self.logger.warning("UI process is already running")
            return False
        
        try:
            command = self._get_ui_command()
            creation_flags = self._get_process_creation_flags()
            
            if self.logger:
                self.logger.info("Starting UI process", {
                    "command": ' '.join(command),
                    "database_path": self.database_path,
                    "platform": platform.system()
                })
            
            # Ensure log directory exists
            self.log_dir.mkdir(parents=True, exist_ok=True)
            stderr_log_path = self.log_dir / "dashboard_stderr.log"

            # Only open stderr log file since stdout goes to console
            self._stderr_log_file = open(stderr_log_path, "w", encoding='utf-8')
            self._stdout_log_file = None  # No longer needed

            # Start the UI process
            if self.logger:
                self.logger.info("About to start UI subprocess", {
                    "command": ' '.join(command),
                    "cwd": str(self.project_root),
                    "creation_flags": creation_flags
                })
            
            # For UI dashboard, we want output to go to the console window, not log files
            # Only redirect stderr to log file to capture errors
            self._process = subprocess.Popen(
                command,
                creationflags=creation_flags,
                cwd=self.project_root,
                stdout=None,  # Let stdout go to the console window
                stderr=self._stderr_log_file  # Keep stderr logging for error capture
            )
            
            # Give the process a moment to start
            time.sleep(2.0)  # Increased wait time for debugging
            
            # Check if process is still running
            poll_result = self._process.poll()
            if poll_result is None:
                self._is_running = True
                if self.logger:
                    self.logger.info("UI process started successfully", {
                        "pid": self._process.pid
                    })
                return True
            else:
                # Process failed to start - read error logs immediately
                self._stderr_log_file.flush()
                self._stdout_log_file.flush()
                
                # Read the error from stderr log
                try:
                    with open(stderr_log_path, 'r', encoding='utf-8') as f:
                        stderr_content = f.read()
                    # stdout_log_file is no longer used since stdout goes to console
                    stdout_content = "Stdout redirected to console window"
                except Exception:
                    stderr_content = "Could not read stderr log"
                    stdout_content = "Stdout redirected to console window"
                
                if self.logger:
                    self.logger.error("UI process failed to start. Check dashboard logs for details.", {
                        "stderr_log": str(stderr_log_path),
                        "return_code": poll_result,
                        "stderr_content": stderr_content[:500]  # First 500 chars
                    })
                self._process = None
                return False
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to start UI process", {"error": str(e)})
            self._process = None
            return False
    
    def stop(self, timeout: float = 10.0) -> bool:
        """Stops the UI process gracefully, with a specified timeout.

        Args:
            timeout (float, optional): The maximum time to wait for graceful shutdown. Defaults to 10.0.

        Returns:
            bool: True if the process stopped successfully, False otherwise.
        """
        # Always try to close file handles, regardless of process state.
        if self._stderr_log_file:
            try: self._stderr_log_file.close()
            except Exception: pass
            self._stderr_log_file = None

        if not self._is_running or not self._process:
            return True
        
        try:
            if self.logger:
                self.logger.info("Stopping UI process", {"pid": self._process.pid})
            
            # Try graceful termination first
            self._process.terminate()
            
            try:
                self._process.wait(timeout=timeout)
                if self.logger:
                    self.logger.info("UI process terminated gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if graceful termination fails
                if self.logger:
                    self.logger.warning("UI process did not terminate gracefully, forcing kill")
                self._process.kill()
                self._process.wait()
            
            self._is_running = False
            self._process = None
            return True
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to stop UI process", {"error": str(e)})
            return False
    
    def is_running(self) -> bool:
        """Checks if the UI process is currently running.

        Returns:
            bool: True if the process is running, False otherwise.
        """
        if not self._process or not self._is_running:
            return False
        
        # Check if process is still alive
        if self._process.poll() is not None:
            # Process has terminated
            self._is_running = False
            if self.logger:
                self.logger.info("UI process has terminated", {
                    "return_code": self._process.returncode
                })
            return False
        
        return True
    
    def get_process_info(self) -> Dict[str, Any]:
        """Returns a dictionary with information about the managed process.

        Returns:
            Dict[str, Any]: A dictionary containing process information.
        """
        if not self._process:
            return {
                "status": "not_started",
                "pid": None,
                "is_running": False
            }
        
        return {
            "status": "running" if self.is_running() else "terminated",
            "pid": self._process.pid,
            "is_running": self.is_running(),
            "return_code": self._process.returncode
        }
    
    def restart(self) -> bool:
        """Restarts the UI process.

        Returns:
            bool: True if the restart was successful, False otherwise.
        """
        if self.logger:
            self.logger.info("Restarting UI process")
        
        # Stop current process
        if not self.stop():
            if self.logger:
                self.logger.error("Failed to stop UI process for restart")
            return False
        
        # Wait a moment before restarting
        time.sleep(1.0)
        
        # Start new process
        return self.start()
    
    def _get_ui_command(self) -> list[str]:
        """Constructs the command to launch the UI process.

        Returns:
            list[str]: A list of command arguments.
        """
        command = [
            sys.executable,
            "-m", "src.ui.dashboard",
            self.database_path
        ]
        if self.config_path:
            command.extend(["--config", str(self.config_path)])
        return command
    
    def _get_process_creation_flags(self) -> int:
        """Gets the appropriate process creation flags based on the platform.

        Returns:
            int: The process creation flags.
        """
        if platform.system() == "Windows":
            # CREATE_NEW_CONSOLE flag to open a new console window
            return subprocess.CREATE_NEW_CONSOLE
        else:
            # No special flags needed for Unix-like systems
            return 0