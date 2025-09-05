# =====================================================================================
# Target File: src/core/worker.py
# Source Reference: src/worker.py, src/main.py
# =====================================================================================

from pathlib import Path
from typing import Any, Dict

from src.database.connection import DatabaseConnection
from src.repositories.case_repo import CaseRepository
from src.repositories.gpu_repo import GpuRepository
from src.handlers.local_handler import LocalHandler
from src.handlers.remote_handler import RemoteHandler
from src.infrastructure.logging_handler import StructuredLogger
from src.infrastructure.process_manager import CommandExecutor
from src.utils.retry_policy import RetryPolicy
from src.infrastructure.gpu_monitor import GpuMonitor
from src.core.workflow_manager import WorkflowManager
from src.config.settings import Settings, DatabaseConfig, HandlerConfig, LoggingConfig


def worker_main(case_id: str, case_path: Path, config_dict: Dict[str, Any]) -> None:
    """
    Acts as the "assembly line" that creates all dependency objects for a single case
    and injects them into the WorkflowManager to start the process.

    FROM: Migrated from the existing `worker_main` in `worker.py` and the object
          initialization logic from `main.py`.

    RESPONSIBILITY:
    - Create all objects (DatabaseConnection, repositories, handlers, etc.)
    - Inject them into WorkflowManager
    - Call run_workflow()
    - Include 'Fail-Fast' path validation logic

    Args:
        case_id: Unique identifier for the case
        case_path: Path to the case directory
        config_dict: Configuration dictionary containing all settings
    """
    settings = Settings()
    settings._yaml_config = config_dict

    logging_config = _create_logging_config(config_dict)
    logger = StructuredLogger(f"worker_{case_id}", config=logging_config)

    db_connection = None
    try:
        _validate_case_path(case_path, logger)

        db_config = _create_database_config(config_dict)
        db_connection = DatabaseConnection(
            db_path=db_config.db_path,
            config=db_config,
            logger=logger
        )

        case_repo = CaseRepository(db_connection, logger)
        gpu_repo = GpuRepository(db_connection, logger)

        handler_config = _create_handler_config(config_dict)
        command_executor = CommandExecutor(logger, handler_config.command_timeout)
        retry_policy = RetryPolicy(logger=logger)

        local_handler = LocalHandler(settings, logger, command_executor, retry_policy)
        remote_handler = RemoteHandler(settings, logger, retry_policy)

        workflow_manager = WorkflowManager(
            case_repo=case_repo,
            gpu_repo=gpu_repo,
            local_handler=local_handler,
            remote_handler=remote_handler,
            logger=logger,
            case_id=case_id,
            case_path=case_path,
        )

        workflow_manager.run_workflow()

    except Exception as e:
        logger.error(f"Worker failed for case {case_id}", {"error": str(e), "error_type": type(e).__name__})
        # Optionally re-raise or handle specific exceptions
        raise
    finally:
        if db_connection:
            db_connection.close()
        logger.info(f"Worker finished for case {case_id}")


def _validate_case_path(case_path: Path, logger: StructuredLogger) -> None:
    """
    Performs 'Fail-Fast' validation of the case path.

    FROM: Path validation logic from the original worker implementation.

    Args:
        case_path: Path to validate
        logger: Logger instance for error reporting

    Raises:
        ValueError: If the path is invalid or inaccessible
    """
    if not case_path.exists():
        logger.error(f"Validation failed: Case path does not exist: {case_path}")
        raise ValueError(f"Case path does not exist: {case_path}")
    if not case_path.is_dir():
        logger.error(f"Validation failed: Case path is not a directory: {case_path}")
        raise ValueError(f"Case path is not a directory: {case_path}")


def _create_database_config(config_dict: Dict[str, Any]) -> DatabaseConfig:
    """
    Creates database configuration from the config dictionary.
    """
    db_conf = config_dict.get('database', {})
    paths_conf = config_dict.get('paths', {}).get('local', {})
    base_dir = config_dict.get('paths', {}).get('base_directory', '.')

    db_path_template = paths_conf.get('database_path', 'database/mqi.db')
    db_path = Path(db_path_template.format(base_directory=base_dir))

    cache_size_mb = db_conf.get('cache_size_mb', 2)
    cache_size = -abs(int(cache_size_mb * 1024))

    return DatabaseConfig(
        db_path=db_path,
        timeout=db_conf.get('busy_timeout_ms', 5000) / 1000, # Convert ms to seconds
        journal_mode=db_conf.get('journal_mode', 'WAL'),
        synchronous=db_conf.get('synchronous_mode', 'NORMAL'),
        cache_size=cache_size
    )


def _create_handler_config(config_dict: Dict[str, Any]) -> HandlerConfig:
    """
    Creates handler configuration from the config dictionary.
    """
    app_conf = config_dict.get('application', {})
    return HandlerConfig(
        command_timeout=app_conf.get('local_execution_timeout_seconds', 300)
    )


def _create_logging_config(config_dict: Dict[str, Any]) -> LoggingConfig:
    """
    Creates logging configuration from the config dictionary.
    """
    log_conf = config_dict.get('logging', {})
    paths_conf = config_dict.get('paths', {}).get('local', {})
    base_dir = config_dict.get('paths', {}).get('base_directory', '.')

    log_dir_template = paths_conf.get('log_directory', 'logs')
    log_dir = Path(log_dir_template.format(base_directory=base_dir))

    return LoggingConfig(
        log_level=log_conf.get('level', 'INFO').upper(),
        log_dir=log_dir,
        max_file_size=log_conf.get('max_file_size_mb', 10),
        backup_count=log_conf.get('backup_count', 5),
        structured_logging=log_conf.get('structured_logging', True)
    )