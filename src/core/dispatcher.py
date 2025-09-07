# =====================================================================================
# Target File: src/core/dispatcher.py
# =====================================================================================

from pathlib import Path
from typing import List, Dict, Any

from src.config.settings import Settings
from src.database.connection import DatabaseConnection
from src.repositories.case_repo import CaseRepository
from src.infrastructure.logging_handler import StructuredLogger
from src.domain.enums import CaseStatus

def prepare_beam_jobs(
    case_id: str, case_path: Path, settings: Settings
) -> List[Dict[str, Any]]:
    """
    Scans a case directory for beams, creates records for them in the database,
    and returns a list of jobs to be processed by workers.

    Args:
        case_id: The ID of the parent case.
        case_path: The file system path to the case directory.
        settings: The application settings object.

    Returns:
        A list of dictionaries, each representing a beam job to be executed.
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
            case_repo.update_case_status(case_id, CaseStatus.FAILED, error_message="No beam subdirectories found")
            return []

        logger.info(f"Found {len(beam_paths)} beams to process.", {"case_id": case_id})

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

        logger.info(f"Successfully prepared {len(beam_jobs)} beam jobs for case: {case_id}")

    except Exception as e:
        logger.error("Failed to dispatch beams", {"case_id": case_id, "error": str(e)})
        # Attempt to mark the parent case as failed
        if db_connection:
            try:
                case_repo = CaseRepository(db_connection, logger)
                case_repo.update_case_status(case_id, CaseStatus.FAILED, error_message=str(e))
            except Exception as db_e:
                logger.error("Failed to update case status during dispatch error", {"case_id": case_id, "db_error": str(db_e)})
        return []  # Return empty list on error
    finally:
        if db_connection:
            db_connection.close()

    return beam_jobs
