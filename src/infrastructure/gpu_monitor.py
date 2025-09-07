import subprocess
import csv
import time
import threading
from io import StringIO
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.infrastructure.logging_handler import StructuredLogger
from src.config.constants import NVIDIA_SMI_QUERY_COMMAND
from src.domain.errors import GpuResourceError
from src.handlers.remote_handler import RemoteHandler
from src.repositories.gpu_repo import GpuRepository

class GpuMonitor:
    """
    A long-running service that periodically fetches GPU resource data from a remote
    host and updates a local repository.
    
    FROM: Extracts the `nvidia-smi` result parsing logic from 
          `populate_gpu_resources_from_nvidia_smi` in original `database_handler.py`
          and combines it with a threaded monitoring loop.
    REFACTORING NOTES: This class is now a stateful service. It separates data
                       acquisition (via RemoteHandler) and parsing from data
                       persistence (via GpuRepository).
    """
    
    def __init__(self,
                 logger: StructuredLogger,
                 remote_handler: RemoteHandler,
                 gpu_repository: GpuRepository,
                 update_interval: int = 60):
        """
        Initialize the GpuMonitor service.
        
        Args:
            logger: Logger for recording operations.
            remote_handler: Handler for executing commands on the remote host.
            gpu_repository: Repository for persisting GPU data.
            update_interval: Interval in seconds between GPU data fetches.
        """
        self.logger = logger
        self.remote_handler = remote_handler
        self.gpu_repository = gpu_repository
        self.update_interval = update_interval

        self._shutdown_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the GPU monitoring service in a background thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            self.logger.warning("GPU monitor is already running.")
            return

        self.logger.info("Starting GPU monitoring service.")
        self._shutdown_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop(self) -> None:
        """Stops the GPU monitoring service."""
        if not self._monitor_thread or not self._monitor_thread.is_alive():
            self.logger.warning("GPU monitor is not running.")
            return

        self.logger.info("Stopping GPU monitoring service.")
        self._shutdown_event.set()
        self._monitor_thread.join(timeout=10) # Wait for thread to finish
        
        if self._monitor_thread.is_alive():
            self.logger.error("GPU monitor thread did not shut down cleanly.")

    def _monitor_loop(self) -> None:
        """The main monitoring loop that runs in a separate thread."""
        self.logger.info("GPU monitor loop started.", {"update_interval": self.update_interval})
        while not self._shutdown_event.is_set():
            try:
                self._fetch_and_update_gpus()
            except Exception as e:
                self.logger.error("An error occurred in the GPU monitor loop.", {"error": str(e)})

            # Wait for the next interval, checking for shutdown signal periodically
            self._shutdown_event.wait(self.update_interval)
        
        self.logger.info("GPU monitor loop has shut down.")

    def _fetch_and_update_gpus(self) -> None:
        """Fetches GPU data from the remote host, parses it, and updates the repository."""
        self.logger.debug("Attempting to fetch remote GPU data.")
        
        try:
            # Execute nvidia-smi command remotely
            result = self.remote_handler.execute_remote_command(
                context_id="gpu_monitoring", # A generic ID for this operation
                command=NVIDIA_SMI_QUERY_COMMAND
            )

            if not result.success:
                self.logger.error("Remote nvidia-smi command failed", {
                    "return_code": result.return_code,
                    "error": result.error
                })
                return

            # Parse the CSV output
            gpu_data = self._parse_nvidia_smi_output(result.output)
            
            if not gpu_data:
                self.logger.warning("Nvidia-smi command succeeded but parsing yielded no GPU data.")
                return

            self.logger.info("Successfully fetched and parsed remote GPU data.", {
                "gpu_count": len(gpu_data)
            })

            # Persist the new data to the repository
            self.gpu_repository.update_resources(gpu_data)

        except Exception as e:
            self.logger.error("An unexpected error occurred while fetching GPU data.", {
                "error": str(e)
            })
    
    def _parse_nvidia_smi_output(self, raw_output: str) -> List[Dict[str, Any]]:
        """
        Parse the CSV output from nvidia-smi into structured data.
        
        FROM: The CSV parsing logic from original `populate_gpu_resources_from_nvidia_smi`.
        REFACTORING NOTES: Extracted and cleaned up the parsing logic with better error handling.
        
        Args:
            raw_output: Raw CSV output from nvidia-smi
            
        Returns:
            List of dictionaries with parsed GPU data
        """
        gpu_data = []
        
        try:
            # Parse CSV data
            csv_reader = csv.reader(StringIO(raw_output))
            
            for row_index, row in enumerate(csv_reader):
                if len(row) != 7:  # Expected: uuid, name, mem_total, mem_used, mem_free, temp, util
                    self.logger.warning("Unexpected nvidia-smi output format", {
                        "row_index": row_index,
                        "row_length": len(row),
                        "expected_length": 7,
                        "row_data": row
                    })
                    continue
                
                try:
                    # Parse and validate data
                    gpu_info = {
                        'uuid': row[0].strip(),
                        'name': row[1].strip(),
                        'memory_total': self._parse_memory_value(row[2]),
                        'memory_used': self._parse_memory_value(row[3]),
                        'memory_free': self._parse_memory_value(row[4]),
                        'temperature': self._parse_temperature_value(row[5]),
                        'utilization': self._parse_utilization_value(row[6]),
                        'last_updated': datetime.now()
                    }
                    
                    # Validate parsed data
                    self._validate_gpu_data(gpu_info)
                    
                    gpu_data.append(gpu_info)
                    
                except ValueError as e:
                    self.logger.warning("Failed to parse GPU row", {
                        "row_index": row_index,
                        "row_data": row,
                        "error": str(e)
                    })
                    continue
        
        except csv.Error as e:
            self.logger.error("Failed to parse CSV output", {
                "error": str(e),
                "raw_output": raw_output
            })
            raise GpuResourceError(f"Failed to parse nvidia-smi CSV output: {e}")
        
        return gpu_data
    
    def _parse_memory_value(self, value: str) -> int:
        """Parse memory value, handling 'N/A' and converting to MB."""
        value = value.strip()
        if value.lower() in ['n/a', '', 'null']:
            return 0
        try:
            return int(float(value))
        except ValueError:
            raise ValueError(f"Invalid memory value: {value}")
    
    def _parse_temperature_value(self, value: str) -> int:
        """Parse temperature value, handling 'N/A' cases."""
        value = value.strip()
        if value.lower() in ['n/a', '', 'null']:
            return 0
        try:
            return int(float(value))
        except ValueError:
            raise ValueError(f"Invalid temperature value: {value}")
    
    def _parse_utilization_value(self, value: str) -> int:
        """Parse utilization percentage, handling 'N/A' cases."""
        value = value.strip()
        if value.lower() in ['n/a', '', 'null']:
            return 0
        try:
            return int(float(value))
        except ValueError:
            raise ValueError(f"Invalid utilization value: {value}")
    
    def _validate_gpu_data(self, gpu_info: Dict[str, Any]) -> None:
        """
        Validate parsed GPU data for consistency.
        
        Args:
            gpu_info: Parsed GPU information dictionary
        """
        # Check UUID format
        if not gpu_info['uuid'] or len(gpu_info['uuid']) < 10:
            raise ValueError(f"Invalid GPU UUID: {gpu_info['uuid']}")
        
        # Check memory consistency
        if gpu_info['memory_total'] > 0:
            if gpu_info['memory_used'] + gpu_info['memory_free'] > gpu_info['memory_total'] * 1.1:
                # Allow 10% tolerance for rounding
                self.logger.warning("Memory values inconsistent", {
                    "uuid": gpu_info['uuid'],
                    "total": gpu_info['memory_total'],
                    "used": gpu_info['memory_used'],
                    "free": gpu_info['memory_free']
                })
        
        # Check temperature range
        if gpu_info['temperature'] > 200:  # Unrealistic temperature
            raise ValueError(f"Invalid temperature: {gpu_info['temperature']}°C")
        
        # Check utilization range
        if not (0 <= gpu_info['utilization'] <= 100):
            raise ValueError(f"Invalid utilization: {gpu_info['utilization']}%")

    def check_nvidia_smi_available(self) -> bool:
        """
        Check if nvidia-smi command is available and working.
        
        Returns:
            True if nvidia-smi is available and working
        """
        try:
            result = subprocess.run(
                ['nvidia-smi', '--version'],
                capture_output=True,
                timeout=10,
                check=True
            )
            
            self.logger.debug("nvidia-smi is available", {
                "version_output": result.stdout.strip()
            })
            
            return True
            
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning("nvidia-smi not available", {
                "error": str(e)
            })
            return False