# =====================================================================================
# Target File: src/config/settings.py
# Source Reference: src/config.py
# =====================================================================================

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional
import os
import yaml

@dataclass
class DatabaseConfig:
    """
    Configuration for database settings.
    FROM: Database configuration from original config.py.
    """
    db_path: Path
    timeout: int = 30
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    cache_size: int = -2000  # 2MB cache

@dataclass
class ProcessingConfig:
    """
    Configuration for processing settings.
    FROM: Processing configuration from original config.py.
    """
    max_workers: int = 4
    case_timeout: int = 3600  # 1 hour
    retry_attempts: int = 3
    retry_delay: int = 60  # 1 minute

@dataclass
class GpuConfig:
    """
    Configuration for GPU resource management.
    FROM: GPU configuration from original config.py.
    """
    monitor_interval: int = 30  # seconds
    allocation_timeout: int = 300  # 5 minutes
    memory_threshold: float = 0.9  # 90% memory usage threshold
    temperature_threshold: int = 85  # degrees celsius

@dataclass
class LoggingConfig:
    """
    Configuration for logging settings.
    FROM: Logging configuration from original config.py.
    """
    log_level: str = "INFO"
    log_dir: Path = Path("logs")
    max_file_size: int = 10  # MB
    backup_count: int = 5
    structured_logging: bool = True

@dataclass
class UIConfig:
    """
    Configuration for UI display settings.
    FROM: Display configuration from original config.py.
    """
    refresh_interval: int = 2  # seconds
    max_log_entries: int = 100
    enable_colors: bool = True
    show_gpu_details: bool = True

@dataclass
class HandlerConfig:
    """
    Configuration for local and remote command handlers.
    """
    command_timeout: int = 300 # seconds
    ssh_timeout: int = 60 # seconds

class Settings:
    """
    Main configuration class that loads and manages all settings.
    FROM: Configuration management from original config.py.
    REFACTORING NOTES: Externalized all configuration to be injected via this class.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize settings from environment variables and config file.
        
        Args:
            config_path: Optional path to configuration file
        """
        self._load_from_env()
        if config_path and config_path.exists():
            self._load_from_file(config_path)
    
    def _load_from_env(self) -> None:
        """
        Load configuration from environment variables.
        FROM: Environment configuration loading from original config.py.
        """
        # Database configuration
        self.database = DatabaseConfig(
            db_path=Path(os.getenv("MQI_DB_PATH", "database/mqi.db")),
            timeout=int(os.getenv("MQI_DB_TIMEOUT", "30")),
            journal_mode=os.getenv("MQI_DB_JOURNAL_MODE", "WAL"),
            synchronous=os.getenv("MQI_DB_SYNCHRONOUS", "NORMAL"),
            cache_size=int(os.getenv("MQI_DB_CACHE_SIZE", "-2000"))
        )
        
        # Processing configuration
        self.processing = ProcessingConfig(
            max_workers=int(os.getenv("MQI_MAX_WORKERS", "4")),
            case_timeout=int(os.getenv("MQI_CASE_TIMEOUT", "3600")),
            retry_attempts=int(os.getenv("MQI_RETRY_ATTEMPTS", "3")),
            retry_delay=int(os.getenv("MQI_RETRY_DELAY", "60"))
        )
        
        # GPU configuration
        self.gpu = GpuConfig(
            monitor_interval=int(os.getenv("MQI_GPU_MONITOR_INTERVAL", "30")),
            allocation_timeout=int(os.getenv("MQI_GPU_ALLOCATION_TIMEOUT", "300")),
            memory_threshold=float(os.getenv("MQI_GPU_MEMORY_THRESHOLD", "0.9")),
            temperature_threshold=int(os.getenv("MQI_GPU_TEMP_THRESHOLD", "85"))
        )
        
        # Logging configuration
        self.logging = LoggingConfig(
            log_level=os.getenv("MQI_LOG_LEVEL", "INFO"),
            log_dir=Path(os.getenv("MQI_LOG_DIR", "logs")),
            max_file_size=int(os.getenv("MQI_LOG_MAX_SIZE", "10")),
            backup_count=int(os.getenv("MQI_LOG_BACKUP_COUNT", "5")),
            structured_logging=os.getenv("MQI_STRUCTURED_LOGGING", "true").lower() == "true"
        )
        
        # UI configuration
        self.ui = UIConfig(
            refresh_interval=int(os.getenv("MQI_UI_REFRESH_INTERVAL", "2")),
            max_log_entries=int(os.getenv("MQI_UI_MAX_LOG_ENTRIES", "100")),
            enable_colors=os.getenv("MQI_UI_ENABLE_COLORS", "true").lower() == "true",
            show_gpu_details=os.getenv("MQI_UI_SHOW_GPU_DETAILS", "true").lower() == "true"
        )
    
    def _load_from_file(self, config_path: Path) -> None:
        """
        Load configuration from YAML file.
        FROM: File configuration loading from original config.py.
        
        Args:
            config_path: Path to YAML configuration file
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # Override with YAML values if present
            if 'database' in config_data:
                db_config = config_data['database']
                self.database.cache_size_mb = db_config.get('cache_size_mb', self.database.cache_size)
                self.database.busy_timeout_ms = db_config.get('busy_timeout_ms', 5000)
                self.database.journal_mode = db_config.get('journal_mode', self.database.journal_mode)
                self.database.synchronous_mode = db_config.get('synchronous_mode', self.database.synchronous)
                
            if 'application' in config_data:
                app_config = config_data['application']
                self.processing.max_workers = app_config.get('max_workers', self.processing.max_workers)
                self.processing.scan_interval_seconds = app_config.get('scan_interval_seconds', 60)
                self.processing.polling_interval_seconds = app_config.get('polling_interval_seconds', 300)
                self.processing.local_execution_timeout_seconds = app_config.get('local_execution_timeout_seconds', 300)
                
            if 'dashboard' in config_data:
                dash_config = config_data['dashboard']
                self.ui.auto_start = dash_config.get('auto_start', True)
                self.ui.refresh_interval = dash_config.get('refresh_interval_seconds', self.ui.refresh_interval)
                
            if 'curator' in config_data:
                curator_config = config_data['curator']
                self.gpu.monitor_interval = curator_config.get('gpu_monitor_interval_seconds', self.gpu.monitor_interval)
                self.gpu.gpu_monitor_command = curator_config.get('gpu_monitor_command', '')
                
            if 'retry_policy' in config_data:
                retry_config = config_data['retry_policy']
                self.processing.retry_attempts = retry_config.get('max_retries', self.processing.retry_attempts)
                self.processing.initial_delay_seconds = retry_config.get('initial_delay_seconds', 5)
                self.processing.max_delay_seconds = retry_config.get('max_delay_seconds', 60)
                self.processing.backoff_multiplier = retry_config.get('backoff_multiplier', 2.0)
                
            # Store the full config for access to paths, executables, etc.
            self._yaml_config = config_data
            
        except Exception as e:
            # Log error but continue with defaults
            print(f"Warning: Could not load config file {config_path}: {e}")
            self._yaml_config = {}
    
    def get_case_directories(self) -> Dict[str, Path]:
        """
        Get configured case directories.
        FROM: Case directory configuration from original config.py.
        """
        if hasattr(self, '_yaml_config') and 'paths' in self._yaml_config:
            paths_config = self._yaml_config['paths']
            base_dir = paths_config.get('base_directory', '')
            local_paths = paths_config.get('local', {})
            
            return {
                "scan": Path(local_paths.get('scan_directory', '').format(base_directory=base_dir)),
                "processing": Path(local_paths.get('processing_directory', '').format(base_directory=base_dir, case_id='{case_id}')),
                "raw_output": Path(local_paths.get('raw_output_directory', '').format(base_directory=base_dir, case_id='{case_id}')),
                "final_dicom": Path(local_paths.get('final_dicom_directory', '').format(base_directory=base_dir, case_id='{case_id}'))
            }
        
        return {
            "input": Path(os.getenv("MQI_INPUT_DIR", "cases/input")),
            "processing": Path(os.getenv("MQI_PROCESSING_DIR", "cases/processing")),
            "output": Path(os.getenv("MQI_OUTPUT_DIR", "cases/output")),
            "failed": Path(os.getenv("MQI_FAILED_DIR", "cases/failed"))
        }
    
    def get_database_path(self) -> Path:
        """
        Get database path from YAML config.
        FROM: Database path configuration from config.yaml.
        """
        if hasattr(self, '_yaml_config') and 'paths' in self._yaml_config:
            paths_config = self._yaml_config['paths']
            base_dir = paths_config.get('base_directory', '')
            local_paths = paths_config.get('local', {})
            db_path = local_paths.get('database_path', '').format(base_directory=base_dir)
            if db_path:
                return Path(db_path)
        
        return self.database.db_path
    
    def get_executables(self) -> Dict[str, str]:
        """
        Get executable paths from YAML config.
        FROM: Executable paths configuration from config.yaml.
        """
        if hasattr(self, '_yaml_config') and 'executables' in self._yaml_config:
            executables = self._yaml_config['executables']
            base_dir = self._yaml_config.get('paths', {}).get('base_directory', '')
            
            return {
                "python_interpreter": executables.get('python_interpreter', '').format(base_directory=base_dir),
                "mqi_interpreter": executables.get('mqi_interpreter', '').format(base_directory=base_dir),
                "raw_to_dicom": executables.get('raw_to_dicom', '').format(base_directory=base_dir)
            }
        
        return {}
    
    def get_hpc_connection(self) -> Dict[str, Any]:
        """
        Get HPC connection configuration from YAML config.
        FROM: HPC connection configuration from config.yaml.
        """
        if hasattr(self, '_yaml_config') and 'hpc_connection' in self._yaml_config:
            return self._yaml_config['hpc_connection']
        
        return {}
    
    def get_hpc_paths(self) -> Dict[str, str]:
        """
        Get HPC paths from YAML config.
        FROM: HPC paths configuration from config.yaml.
        """
        if hasattr(self, '_yaml_config') and 'paths' in self._yaml_config:
            return self._yaml_config['paths'].get('hpc', {})
        
        return {}
    
    def get_moqui_tps_parameters(self) -> Dict[str, Any]:
        """
        Get MOQUI TPS parameters from YAML config.
        FROM: MOQUI TPS parameters configuration from config.yaml.
        """
        if hasattr(self, '_yaml_config') and 'moqui_tps_parameters' in self._yaml_config:
            return self._yaml_config['moqui_tps_parameters']
        
        return {}