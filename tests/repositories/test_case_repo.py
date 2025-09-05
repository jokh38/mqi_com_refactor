import unittest
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock

# Add src to path to allow imports
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.repositories.case_repo import CaseRepository
from src.database.connection import DatabaseConnection
from src.domain.enums import CaseStatus, WorkflowStep
from src.domain.models import CaseData
from src.config.settings import DatabaseConfig

class TestCaseRepository(unittest.TestCase):

    def setUp(self):
        """Set up an in-memory SQLite database for each test."""
        self.mock_logger = Mock()

        # Mock config
        self.mock_config = DatabaseConfig(
            db_path=Path(":memory:"),
            timeout=5.0,
            journal_mode="WAL",
            synchronous="NORMAL",
            cache_size=-2000  # 2MB
        )

        # Use in-memory database
        self.db_connection = DatabaseConnection(
            db_path=Path(":memory:"),
            config=self.mock_config,
            logger=self.mock_logger
        )

        # The DatabaseConnection's __init__ already calls init_db
        self.repo = CaseRepository(self.db_connection, self.mock_logger)

    def tearDown(self):
        """Close the database connection after each test."""
        self.db_connection.close()

    def test_add_case(self):
        """Test adding a new case to the database."""
        case_id = "test_case_01"
        case_path = Path("/tmp/test_case_01")

        self.repo.add_case(case_id, case_path)

        # Verify the case was added
        with self.db_connection.transaction() as conn:
            cursor = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
            row = cursor.fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row['case_id'], case_id)
        self.assertEqual(row['case_path'], str(case_path))
        self.assertEqual(row['status'], CaseStatus.PENDING.value)
        self.assertEqual(row['progress'], 0.0)

    def test_get_case(self):
        """Test retrieving a case by its ID."""
        case_id = "test_case_02"
        case_path = Path("/tmp/test_case_02")
        self.repo.add_case(case_id, case_path)

        case_data = self.repo.get_case(case_id)

        self.assertIsNotNone(case_data)
        self.assertIsInstance(case_data, CaseData)
        self.assertEqual(case_data.case_id, case_id)
        self.assertEqual(case_data.case_path, case_path)
        self.assertEqual(case_data.status, CaseStatus.PENDING)

    def test_update_case_status(self):
        """Test updating a case's status and progress."""
        case_id = "test_case_03"
        case_path = Path("/tmp/test_case_03")
        self.repo.add_case(case_id, case_path)

        # Update status and progress
        new_status = CaseStatus.PROCESSING
        new_progress = 50.0
        self.repo.update_case_status(case_id, new_status, progress=new_progress)

        case_data = self.repo.get_case(case_id)
        self.assertEqual(case_data.status, new_status)
        self.assertEqual(case_data.progress, new_progress)

        # Update with error message
        fail_status = CaseStatus.FAILED
        error_msg = "Something went wrong"
        self.repo.update_case_status(case_id, fail_status, error_message=error_msg)

        case_data = self.repo.get_case(case_id)
        self.assertEqual(case_data.status, fail_status)
        self.assertEqual(case_data.error_message, error_msg)

    def test_get_cases_by_status(self):
        """Test retrieving cases filtered by status."""
        # Add cases with different statuses
        self.repo.add_case("case_pending_1", Path("/tmp/p1"))
        self.repo.add_case("case_pending_2", Path("/tmp/p2"))
        self.repo.add_case("case_processing_1", Path("/tmp/proc1"))
        self.repo.update_case_status("case_processing_1", CaseStatus.PROCESSING)

        pending_cases = self.repo.get_cases_by_status(CaseStatus.PENDING)
        self.assertEqual(len(pending_cases), 2)
        self.assertTrue(all(c.status == CaseStatus.PENDING for c in pending_cases))

        processing_cases = self.repo.get_cases_by_status(CaseStatus.PROCESSING)
        self.assertEqual(len(processing_cases), 1)
        self.assertEqual(processing_cases[0].case_id, "case_processing_1")

    def test_get_all_active_cases(self):
        """Test retrieving all cases that are not in a terminal state."""
        self.repo.add_case("case_pending", Path("/tmp/p")) # Active
        self.repo.add_case("case_processing", Path("/tmp/proc")) # Active
        self.repo.add_case("case_completed", Path("/tmp/comp"))
        self.repo.add_case("case_failed", Path("/tmp/fail"))

        self.repo.update_case_status("case_processing", CaseStatus.PROCESSING)
        self.repo.update_case_status("case_completed", CaseStatus.COMPLETED)
        self.repo.update_case_status("case_failed", CaseStatus.FAILED)

        active_cases = self.repo.get_all_active_cases()

        self.assertEqual(len(active_cases), 2)
        active_ids = {c.case_id for c in active_cases}
        self.assertIn("case_pending", active_ids)
        self.assertIn("case_processing", active_ids)

    def test_record_and_get_workflow_steps(self):
        """Test recording and retrieving workflow steps for a case."""
        case_id = "test_workflow_case"
        self.repo.add_case(case_id, Path("/tmp/wf"))

        # Record a few steps
        self.repo.record_workflow_step(case_id, WorkflowStep.PREPROCESSING, "started")
        self.repo.record_workflow_step(
            case_id,
            WorkflowStep.PREPROCESSING,
            "completed",
            metadata={"files_generated": 5}
        )
        self.repo.record_workflow_step(
            case_id,
            WorkflowStep.TPS_GENERATION,
            "failed",
            error_message="CUDA out of memory"
        )

        steps = self.repo.get_workflow_steps(case_id)

        self.assertEqual(len(steps), 3)

        self.assertEqual(steps[0].step, WorkflowStep.PREPROCESSING)
        self.assertEqual(steps[0].status, "started")

        self.assertEqual(steps[1].step, WorkflowStep.PREPROCESSING)
        self.assertEqual(steps[1].status, "completed")
        self.assertEqual(steps[1].metadata, {"files_generated": 5})

        self.assertEqual(steps[2].step, WorkflowStep.TPS_GENERATION)
        self.assertEqual(steps[2].status, "failed")
        self.assertEqual(steps[2].error_message, "CUDA out of memory")

    def test_assign_gpu_to_case(self):
        """Test assigning a GPU UUID to a case."""
        case_id = "test_gpu_assign_case"
        gpu_uuid = "GPU-xyz-123"
        self.repo.add_case(case_id, Path("/tmp/gpu_case"))

        self.repo.assign_gpu_to_case(case_id, gpu_uuid)

        case_data = self.repo.get_case(case_id)
        self.assertEqual(case_data.assigned_gpu, gpu_uuid)

if __name__ == '__main__':
    unittest.main()
