# =====================================================================================
# Target File: src/repositories/case_repo.py
# Source Reference: src/database_handler.py (cases table operations)
# =====================================================================================

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.database.connection import DatabaseConnection
from src.domain.enums import CaseStatus, WorkflowStep
from src.domain.models import CaseData, WorkflowStepRecord
from src.infrastructure.logging_handler import StructuredLogger
from src.repositories.base import BaseRepository


class CaseRepository(BaseRepository):
    """
    Manages all CRUD operations for the 'cases' table.

    FROM: Extracts all case-related methods (e.g., `add_case`, `update_case_status`)
          from the original `database_handler.py`.
    REFACTORING NOTES: Implements Repository Pattern for case data access.
    """

    def __init__(self, db_connection: DatabaseConnection, logger: StructuredLogger):
        """
        Initializes the case repository with injected database connection.

        Args:
            db_connection: Database connection manager
            logger: Logger for recording operations
        """
        super().__init__(db_connection, logger)

    def add_case(self, case_id: str, case_path: Path) -> None:
        """
        Adds a new case to the 'cases' table.

        FROM: Migrated from the `add_case` method in `database_handler.py`.
        REFACTORING NOTES: Uses `CaseStatus.PENDING` enum for status consistency.

        Args:
            case_id: Unique identifier for the case
            case_path: Path to the case directory
        """
        self._log_operation("add_case", case_id, case_path=str(case_path))

        query = """
            INSERT INTO cases (case_id, case_path, status, progress, created_at,
                               updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """

        self._execute_query(
            query, (case_id, str(case_path), CaseStatus.PENDING.value, 0.0)
        )

        self.logger.info(
            "Case added successfully",
            {
                "case_id": case_id,
                "case_path": str(case_path),
                "status": CaseStatus.PENDING.value,
            },
        )

    def update_case_status(
        self,
        case_id: str,
        status: CaseStatus,
        progress: float = None,
        error_message: str = None,
    ) -> None:
        """
        Updates the status and progress of a case.

        FROM: Migrated from `update_case_status` method in `database_handler.py`.

        Args:
            case_id: Case identifier
            status: New case status
            progress: Optional progress percentage (0-100)
            error_message: Optional error message for failed cases
        """
        self._log_operation(
            "update_case_status", case_id, status=status.value, progress=progress
        )

        set_clauses = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
        params = [status.value]

        if progress is not None:
            set_clauses.append("progress = ?")
            params.append(progress)

        if error_message is not None:
            set_clauses.append("error_message = ?")
            params.append(error_message)

        params.append(case_id)

        query = f"UPDATE cases SET {', '.join(set_clauses)} WHERE case_id = ?"

        self._execute_query(query, tuple(params))

        self.logger.info(
            "Case status updated",
            {"case_id": case_id, "status": status.value, "progress": progress},
        )

    def get_case(self, case_id: str) -> Optional[CaseData]:
        """
        Retrieves a single case by its ID.

        FROM: Migrated from case retrieval logic in `database_handler.py`.

        Args:
            case_id: Case identifier

        Returns:
            CaseData object if found, None otherwise
        """
        self._log_operation("get_case", case_id)

        query = """
            SELECT case_id, case_path, status, progress, created_at,
                   updated_at, error_message, assigned_gpu
            FROM cases
            WHERE case_id = ?
        """

        row = self._execute_query(query, (case_id,), fetch_one=True)

        if row:
            return CaseData(
                case_id=row["case_id"],
                case_path=Path(row["case_path"]),
                status=CaseStatus(row["status"]),
                progress=row["progress"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=(
                    datetime.fromisoformat(row["updated_at"])
                    if row["updated_at"]
                    else None
                ),
                error_message=row["error_message"],
                assigned_gpu=row["assigned_gpu"],
            )

        return None

    def get_cases_by_status(self, status: CaseStatus) -> List[CaseData]:
        """
        Retrieves all cases with a specific status.

        FROM: Migrated from status-based case queries in `database_handler.py`.

        Args:
            status: Case status to filter by

        Returns:
            List of CaseData objects matching the status
        """
        self._log_operation("get_cases_by_status", status=status.value)

        query = """
            SELECT case_id, case_path, status, progress, created_at,
                   updated_at, error_message, assigned_gpu
            FROM cases
            WHERE status = ?
            ORDER BY created_at ASC
        """

        rows = self._execute_query(query, (status.value,), fetch_all=True)

        cases = []
        for row in rows:
            cases.append(
                CaseData(
                    case_id=row["case_id"],
                    case_path=Path(row["case_path"]),
                    status=CaseStatus(row["status"]),
                    progress=row["progress"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=(
                        datetime.fromisoformat(row["updated_at"])
                        if row["updated_at"]
                        else None
                    ),
                    error_message=row["error_message"],
                    assigned_gpu=row["assigned_gpu"],
                )
            )

        return cases

    def record_workflow_step(
        self,
        case_id: str,
        step: WorkflowStep,
        status: str,
        error_message: str = None,
        metadata: Dict[str, Any] = None,
        step_name: str = None,  # Added for backward compatibility
        details: str = None,    # Added for backward compatibility
    ) -> None:
        """
        Records the start or completion of a workflow step.

        FROM: Migrated from workflow step recording in `database_handler.py`.

        Args:
            case_id: Case identifier
            step: Workflow step being recorded
            status: Step status ('started', 'completed', 'failed')
            error_message: Optional error message for failed steps
            metadata: Optional metadata dictionary
        """
        # Handle backward compatibility
        if step_name is not None:
            # Try to convert step_name to WorkflowStep enum
            try:
                step = WorkflowStep(step_name)
            except ValueError:
                # If step_name doesn't match enum, use step parameter
                pass
        
        if details and not error_message:
            error_message = details

        self._log_operation(
            "record_workflow_step", case_id, step=step.value, status=status
        )

        query = """
            INSERT INTO workflow_steps
            (case_id, step, started_at, status, error_message, metadata)
            VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
        """

        metadata_json = json.dumps(metadata) if metadata else None

        self._execute_query(
            query, (case_id, step.value, status, error_message, metadata_json)
        )

    def get_workflow_steps(self, case_id: str) -> List[WorkflowStepRecord]:
        """
        Retrieves all workflow steps for a given case.

        FROM: Workflow step retrieval from `database_handler.py`.

        Args:
            case_id: Case identifier

        Returns:
            List of WorkflowStepRecord objects
        """
        self._log_operation("get_workflow_steps", case_id)

        query = """
            SELECT case_id, step, started_at, completed_at, status,
                   error_message, metadata
            FROM workflow_steps
            WHERE case_id = ?
            ORDER BY started_at ASC
        """

        rows = self._execute_query(query, (case_id,), fetch_all=True)

        steps = []
        for row in rows:
            metadata = json.loads(row["metadata"]) if row["metadata"] else None

            steps.append(
                WorkflowStepRecord(
                    case_id=row["case_id"],
                    step=WorkflowStep(row["step"]),
                    started_at=datetime.fromisoformat(row["started_at"]),
                    completed_at=(
                        datetime.fromisoformat(row["completed_at"])
                        if row["completed_at"]
                        else None
                    ),
                    status=row["status"],
                    error_message=row["error_message"],
                    metadata=metadata,
                )
            )

        return steps

    def assign_gpu_to_case(self, case_id: str, gpu_uuid: str) -> None:
        """
        Assigns a GPU to a specific case.

        FROM: GPU assignment logic from `database_handler.py`.

        Args:
            case_id: Case identifier
            gpu_uuid: UUID of the GPU to assign
        """
        self._log_operation("assign_gpu_to_case", case_id, gpu_uuid=gpu_uuid)

        query = (
            "UPDATE cases SET assigned_gpu = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE case_id = ?"
        )

        self._execute_query(query, (gpu_uuid, case_id))

        self.logger.info(
            "GPU assigned to case", {"case_id": case_id, "gpu_uuid": gpu_uuid}
        )

    def get_all_active_cases(self) -> List[CaseData]:
        """
        Retrieves all cases that are currently active (not completed or failed).

        FROM: Active case queries from original display handler logic.

        Returns:
            List of active CaseData objects
        """
        self._log_operation("get_all_active_cases")

        active_statuses = [
            CaseStatus.PENDING.value,
            CaseStatus.PREPROCESSING.value,
            CaseStatus.PROCESSING.value,
            CaseStatus.POSTPROCESSING.value,
        ]

        placeholders = ",".join(["?" for _ in active_statuses])
        query = f"""
            SELECT case_id, case_path, status, progress, created_at,
                   updated_at, error_message, assigned_gpu
            FROM cases
            WHERE status IN ({placeholders})
            ORDER BY created_at ASC
        """

        rows = self._execute_query(query, tuple(active_statuses), fetch_all=True)

        cases = []
        for row in rows:
            cases.append(
                CaseData(
                    case_id=row["case_id"],
                    case_path=Path(row["case_path"]),
                    status=CaseStatus(row["status"]),
                    progress=row["progress"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=(
                        datetime.fromisoformat(row["updated_at"])
                        if row["updated_at"]
                        else None
                    ),
                    error_message=row["error_message"],
                    assigned_gpu=row["assigned_gpu"],
                )
            )

        return cases
