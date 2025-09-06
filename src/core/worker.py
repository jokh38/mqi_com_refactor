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
from src.core.tps_generator import TpsGenerator
from src.config.settings import Settings, DatabaseConfig, HandlerConfig, LoggingConfig


def worker_main(case_id: str, case_path: Path, settings: Settings) -> None:
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
        settings: Settings object containing all configuration
    """
    logger = StructuredLogger(f"worker_{case_id}", config=settings.logging)

    db_connection = None
    try:
        _validate_case_path(case_path, logger)

        # Use database path from settings
        db_path = settings.get_database_path()
        db_connection = DatabaseConnection(
            db_path=db_path,
            config=settings.database,
            logger=logger
        )
        # Initialize database schema
        db_connection.init_db()

        case_repo = CaseRepository(db_connection, logger)
        gpu_repo = GpuRepository(db_connection, logger)

        # Create handler dependencies
        command_executor = CommandExecutor(logger, settings.processing.local_execution_timeout_seconds)
        retry_policy = RetryPolicy(logger=logger)

        local_handler = LocalHandler(settings, logger, command_executor, retry_policy)
        remote_handler = RemoteHandler(settings, logger, retry_policy)
        
        # Create TPS generator
        tps_generator = TpsGenerator(settings, logger)

        workflow_manager = WorkflowManager(
            case_repo=case_repo,
            gpu_repo=gpu_repo,
            local_handler=local_handler,
            remote_handler=remote_handler,
            tps_generator=tps_generator,
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


