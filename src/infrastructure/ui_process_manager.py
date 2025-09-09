# =====================================================================================
# Target File: src/infrastructure/ui_process_manager.py
# Source Reference: jsons/display_process_manager.json
# =====================================================================================
"""!
@file ui_process_manager.py
@brief Manages the UI subprocess lifecycle, handling its creation, monitoring, and termination.
"""

import subprocess
import sys
import platform
import time
from typing import Optional, Dict, Any
from pathlib import Path

from src.infrastructure.logging_handler import StructuredLogger
from src.config.settings import Settings


class UIProcessManager:
    """!
    @brief A professional manager for the UI subprocess lifecycle, handling its creation,
           monitoring, and clean termination with separate console window support.
    @details This class is responsible for launching and managing the UI as a separate process
             with proper console window handling on Windows systems.
    """
    
    def __init__(self, database_path: str, config: Settings, logger: StructuredLogger):
        """!
        @brief Initializes the UIProcessManager.
        @param database_path: The resolved path to the SQLite database file.
        @param config: The application configuration object.
        @param logger: A logger instance for status messages.
        """
        self.database_path = database_path
        self.config = config
        self.logger = logger
        self.project_root = Path(__file__).parent.parent.parent
        self._process: Optional[subprocess.Popen] = None
        self._is_running = False
    
    def start(self) -> bool:
        """!
        @brief Starts the UI as an independent process.
        @details Creates a new console window on Windows systems as per original behavior.
        @return True if the process started successfully, False otherwise.
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
            
            # Start the UI process
            self._process = subprocess.Popen(
                command,
                creationflags=creation_flags,
                cwd=self.project_root
            )
            
            # Give the process a moment to start
            time.sleep(0.5)
            
            # Check if process is still running
            if self._process.poll() is None:
                self._is_running = True
                if self.logger:
                    self.logger.info("UI process started successfully", {
                        "pid": self._process.pid
                    })
                return True
            else:
                # Process failed to start
                if self.logger:
                    self.logger.error("UI process failed to start", {
                        "return_code": self._process.returncode
                    })
                self._process = None
                return False
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to start UI process", {"error": str(e)})
            self._process = None
            return False
    
    def stop(self, timeout: float = 10.0) -> bool:
        """!
        @brief Stops the UI process gracefully, with a specified timeout.
        @param timeout: The maximum time to wait for graceful shutdown.
        @return True if the process stopped successfully, False otherwise.
        """
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
        """!
        @brief Checks if the UI process is currently running.
        @return True if the process is running, False otherwise.
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
        """!
        @brief Returns a dictionary with information about the managed process.
        @return A dictionary containing process information.
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
        """!
        @brief Restarts the UI process.
        @return True if the restart was successful, False otherwise.
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
        """!
        @brief Constructs the command to launch the UI process.
        @return A list of command arguments.
        """
        return [
            sys.executable,
            "-m", "src.ui.dashboard",
            self.database_path
        ]
    
    def _get_process_creation_flags(self) -> int:
        """!
        @brief Gets the appropriate process creation flags based on the platform.
        @return The process creation flags.
        """
        if platform.system() == "Windows":
            # CREATE_NEW_CONSOLE flag to open a new console window
            return subprocess.CREATE_NEW_CONSOLE
        else:
            # No special flags needed for Unix-like systems
            return 0