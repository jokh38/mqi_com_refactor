# =====================================================================================
# Target File: src/core/dispatcher.py
# =====================================================================================
"""Contains logic for dispatching cases and beams for processing."""

from pathlib import Path
from typing import List, Dict, Any

from src.config.settings import Settings
from src.database.connection import DatabaseConnection
from src.repositories.case_repo import CaseRepository
from src.infrastructure.logging_handler import StructuredLogger
from src.domain.enums import CaseStatus, WorkflowStep
from src.handlers.local_handler import LocalHandler
from src.infrastructure.process_manager import CommandExecutor
from src.utils.retry_policy import RetryPolicy
from src.domain.errors import ProcessingError


def run_case_level_preprocessing(
        case_id: str, case_path: Path,
        settings: Settings) -> bool:
    """Runs the mqi_interpreter for the entire case before beam-level processing.

    Args:
        case_id (str): The ID of the case.
        case_path (Path): The file system path to the case directory.
        settings (Settings): The application settings object.

    Returns:
        bool: True if preprocessing was successful, False otherwise.
    """
    logger = StructuredLogger(f"dispatcher_{case_id}", config=settings.logging)
    db_connection = None
    try:
        # Setup dependencies for LocalHandler
        command_executor = CommandExecutor(logger)
        retry_policy = RetryPolicy(
            max_attempts=settings.retry_policy.max_retries,
            base_delay=settings.retry_policy.initial_delay_seconds,
            max_delay=settings.retry_policy.max_delay_seconds,
            backoff_multiplier=settings.retry_policy.backoff_multiplier,
            logger=logger,
        )
        local_handler = LocalHandler(
            settings=settings,
            logger=logger,
            command_executor=command_executor,
            retry_policy=retry_policy,
        )

        # Establish database connection to record workflow step
        db_path = settings.get_database_path()
        db_connection = DatabaseConnection(
            db_path=db_path, config=settings.database, logger=logger
        )
        case_repo = CaseRepository(db_connection, logger)

        logger.info(f"Starting case-level preprocessing for: {case_id}")
        case_repo.record_workflow_step(
            case_id=case_id,
            step=WorkflowStep.PREPROCESSING,
            status="started",
            metadata={"message": "Running mqi_interpreter for the whole case."}
        )

        # The output of the case-level interpreter should go into the case directory itself
        # from where beam-level workflows can pick up the results.
        result = local_handler.run_mqi_interpreter(
            beam_directory=case_path,
            output_dir=case_path,
            case_id=case_id
        )

        if not result.success:
            error_message = (
                f"Case-level mqi_interpreter failed for '{case_id}'. "
                f"Error: {result.error}")
            raise ProcessingError(error_message)

        # Verify that CSV files were created for each beam
        beam_dirs = [d for d in case_path.iterdir() if d.is_dir()]
        for beam_dir in beam_dirs:
            if not any(beam_dir.glob("*.csv")):
                logger.warning(
                    f"No CSV files found in beam directory {beam_dir.name} "
                    f"after case-level preprocessing.")
                # Depending on requirements, this could be a fatal error for the case.
                # For now, we'll log a warning and proceed.

        logger.info(
            f"Case-level preprocessing completed successfully for: {case_id}")
        case_repo.record_workflow_step(
            case_id=case_id,
            step=WorkflowStep.PREPROCESSING,
            status="completed",
            metadata={
                "message": "mqi_interpreter finished successfully for the whole case."
            })
        return True

    except Exception as e:
        logger.error("Case-level preprocessing failed",
                     {"case_id": case_id, "error": str(e)})
        if db_connection:
            try:
                case_repo = CaseRepository(db_connection, logger)
                case_repo.update_case_status(case_id,
                                             CaseStatus.FAILED,
                                             error_message=str(e))
                case_repo.record_workflow_step(case_id=case_id,
                                               step=WorkflowStep.PREPROCESSING,
                                               status="failed",
                                               metadata={"error": str(e)})
            except Exception as db_e:
                logger.error(
                    "Failed to update case status during preprocessing error",
                    {"case_id": case_id, "db_error": str(db_e)})
        return False
    finally:
        if db_connection:
            db_connection.close()


def prepare_beam_jobs(
    case_id: str, case_path: Path, settings: Settings
) -> List[Dict[str, Any]]:
    """Scans a case directory for beams, creates records for them in the database,
    and returns a list of jobs to be processed by workers.

    Args:
        case_id (str): The ID of the parent case.
        case_path (Path): The file system path to the case directory.
        settings (Settings): The application settings object.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, each representing a beam job to be executed.
        Returns an empty list if no beams are found or an error occurs.
    """
    logger = StructuredLogger(f"dispatcher_{case_id}", config=settings.logging)
    db_connection = None
    beam_jobs = []

    try:
        logger.info(f"Dispatching beams for case: {case_id}")

        # Establish database connection
        db_path = settings.get_database_path()
        db_connection = DatabaseConnection(
            db_path=db_path, config=settings.database, logger=logger
        )
        case_repo = CaseRepository(db_connection, logger)

        # Update parent case status to PROCESSING
        case_repo.update_case_status(case_id, CaseStatus.PROCESSING)

        # Scan for beam subdirectories
        beam_paths = [d for d in case_path.iterdir() if d.is_dir()]

        if not beam_paths:
            logger.warning("No beam subdirectories found.", {"case_id": case_id})
            # If no beams, maybe the case is failed or completed differently
            case_repo.update_case_status(
                case_id,
                CaseStatus.FAILED,
                error_message="No beam subdirectories found")
            return []

        logger.info(f"Found {len(beam_paths)} beams to process.",
                    {"case_id": case_id})

        for beam_path in beam_paths:
            beam_name = beam_path.name
            beam_id = f"{case_id}_{beam_name}"

            # Create a record for the beam in the database
            case_repo.create_beam_record(
                beam_id=beam_id, parent_case_id=case_id, beam_path=beam_path
            )
            logger.info(f"Created DB record for beam: {beam_id}")

            # Add job to the list
            beam_jobs.append({"beam_id": beam_id, "beam_path": beam_path})

        logger.info(
            f"Successfully prepared {len(beam_jobs)} beam jobs for case: {case_id}")

    except Exception as e:
        logger.error("Failed to dispatch beams",
                     {"case_id": case_id, "error": str(e)})
        # Attempt to mark the parent case as failed
        if db_connection:
            try:
                case_repo = CaseRepository(db_connection, logger)
                case_repo.update_case_status(case_id,
                                             CaseStatus.FAILED,
                                             error_message=str(e))
            except Exception as db_e:
                logger.error(
                    "Failed to update case status during dispatch error",
                    {"case_id": case_id, "db_error": str(db_e)})
        return []  # Return empty list on error
    finally:
        if db_connection:
            db_connection.close()

    return beam_jobs
