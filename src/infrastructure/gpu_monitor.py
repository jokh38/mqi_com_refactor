# =====================================================================================
# Target File: src/infrastructure/gpu_monitor.py
# Source Reference: src/database_handler.py (nvidia-smi parsing logic)
# =====================================================================================

import subprocess
import csv
from io import StringIO
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.infrastructure.logging_handler import StructuredLogger
from src.config.constants import NVIDIA_SMI_COMMAND
from src.domain.errors import GpuResourceError

class GpuMonitor:
    """
    Handles GPU resource monitoring and data parsing from nvidia-smi.
    
    FROM: Extracts the `nvidia-smi` result parsing logic from 
          `populate_gpu_resources_from_nvidia_smi` in original `database_handler.py`.
    REFACTORING NOTES: Separates data acquisition from data persistence.
                      This class only handles parsing, while GpuRepository handles storage.
    """
    
    def __init__(self, logger: StructuredLogger, timeout: int = 30):
        """
        Initialize GPU monitor.
        
        Args:
            logger: Logger for recording operations
            timeout: Command execution timeout in seconds
        """
        self.logger = logger
        self.timeout = timeout
    
    def get_gpu_data(self) -> List[Dict[str, Any]]:
        """
        Retrieve and parse current GPU resource data from nvidia-smi.
        
        FROM: The CSV parsing logic from `populate_gpu_resources_from_nvidia_smi` 
              in original `database_handler.py`.
        
        Returns:
            List of dictionaries containing GPU information
        """
        self.logger.debug("Fetching GPU data from nvidia-smi")
        
        try:
            # Execute nvidia-smi command
            raw_output = self._execute_nvidia_smi()
            
            # Parse CSV output
            gpu_data = self._parse_nvidia_smi_output(raw_output)
            
            self.logger.info("GPU data retrieved successfully", {
                "gpu_count": len(gpu_data)
            })
            
            return gpu_data
            
        except subprocess.TimeoutExpired:
            self.logger.error("nvidia-smi command timed out", {
                "timeout": self.timeout
            })
            raise GpuResourceError(f"nvidia-smi command timed out after {self.timeout} seconds")
            
        except subprocess.CalledProcessError as e:
            self.logger.error("nvidia-smi command failed", {
                "return_code": e.returncode,
                "stderr": e.stderr.decode() if e.stderr else None
            })
            raise GpuResourceError(f"nvidia-smi command failed: {e}")
            
        except Exception as e:
            self.logger.error("Failed to retrieve GPU data", {
                "error": str(e)
            })
            raise GpuResourceError(f"Failed to retrieve GPU data: {e}")
    
    def _execute_nvidia_smi(self) -> str:
        """
        Execute the nvidia-smi command and return raw output.
        
        FROM: Command execution logic from original GPU monitoring.
        
        Returns:
            Raw CSV output from nvidia-smi
        """
        result = subprocess.run(
            NVIDIA_SMI_COMMAND.split(),
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=True
        )
        
        return result.stdout
    
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
                "version_output": result.stdout.decode().strip()
            })
            
            return True
            
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.logger.warning("nvidia-smi not available", {
                "error": str(e)
            })
            return False