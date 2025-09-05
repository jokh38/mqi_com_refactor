from pathlib import Path
import pytest

from src.repositories.case_repo import CaseRepository
from src.domain.enums import CaseStatus, WorkflowStep
from src.domain.models import CaseData


@pytest.fixture
def case_repo(db_connection, logger):
    """Pytest fixture for creating a CaseRepository instance."""
    return CaseRepository(db_connection, logger)


def test_add_case(case_repo, db_connection):
    """Tests that a new case can be added to the database."""
    case_id = "case_001"
    case_path = Path("/path/to/case_001")
    case_repo.add_case(case_id, case_path)

    # Verify the case was added correctly
    with db_connection.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["case_id"] == case_id
        assert row["case_path"] == str(case_path)
        assert row["status"] == CaseStatus.PENDING.value
        assert row["progress"] == 0.0


def test_update_case_status(case_repo, db_connection):
    """Tests updating the status and progress of a case."""
    case_id = "case_002"
    case_repo.add_case(case_id, Path("/path/to/case_002"))

    # Update status and progress
    case_repo.update_case_status(case_id, CaseStatus.PROCESSING, progress=50.0)

    # Verify the update
    case = case_repo.get_case(case_id)
    assert case is not None
    assert case.status == CaseStatus.PROCESSING
    assert case.progress == 50.0

    # Test updating with an error message
    error_msg = "Something went wrong"
    case_repo.update_case_status(case_id, CaseStatus.FAILED, error_message=error_msg)
    case = case_repo.get_case(case_id)
    assert case is not None
    assert case.status == CaseStatus.FAILED
    assert case.error_message == error_msg


def test_get_case(case_repo):
    """Tests retrieving a single case by its ID."""
    case_id = "case_003"
    case_repo.add_case(case_id, Path("/path/to/case_003"))

    case = case_repo.get_case(case_id)
    assert case is not None
    assert isinstance(case, CaseData)
    assert case.case_id == case_id
    assert case.status == CaseStatus.PENDING

    # Test getting a non-existent case
    non_existent_case = case_repo.get_case("non_existent_id")
    assert non_existent_case is None


def test_get_cases_by_status(case_repo):
    """Tests retrieving cases filtered by status."""
    # Add cases with different statuses
    case_repo.add_case("case_pending_1", Path("/path/pending1"))
    case_repo.add_case("case_pending_2", Path("/path/pending2"))
    case_repo.add_case("case_processing_1", Path("/path/processing1"))
    case_repo.update_case_status("case_processing_1", CaseStatus.PROCESSING)

    pending_cases = case_repo.get_cases_by_status(CaseStatus.PENDING)
    assert len(pending_cases) == 2
    assert all(c.status == CaseStatus.PENDING for c in pending_cases)

    processing_cases = case_repo.get_cases_by_status(CaseStatus.PROCESSING)
    assert len(processing_cases) == 1
    assert processing_cases[0].case_id == "case_processing_1"

    completed_cases = case_repo.get_cases_by_status(CaseStatus.COMPLETED)
    assert len(completed_cases) == 0


def test_record_and_get_workflow_steps(case_repo):
    """Tests recording and retrieving workflow steps for a case."""
    case_id = "case_workflow_001"
    case_repo.add_case(case_id, Path("/path/workflow1"))

    # Record some steps
    case_repo.record_workflow_step(case_id, WorkflowStep.PREPROCESSING, "started")
    case_repo.record_workflow_step(
        case_id, WorkflowStep.PREPROCESSING, "completed", metadata={"files": 5}
    )
    case_repo.record_workflow_step(
        case_id, WorkflowStep.TPS_GENERATION, "failed", error_message="crash"
    )

    steps = case_repo.get_workflow_steps(case_id)
    assert len(steps) == 3
    assert steps[0].step == WorkflowStep.PREPROCESSING
    assert steps[0].status == "started"
    assert steps[1].metadata == {"files": 5}
    assert steps[2].step == WorkflowStep.TPS_GENERATION
    assert steps[2].error_message == "crash"


def test_assign_gpu_to_case(case_repo):
    """Tests assigning a GPU to a case."""
    case_id = "case_gpu_assign_001"
    gpu_uuid = "GPU-12345"
    case_repo.add_case(case_id, Path("/path/gpu_case"))

    case_repo.assign_gpu_to_case(case_id, gpu_uuid)

    case = case_repo.get_case(case_id)
    assert case is not None
    assert case.assigned_gpu == gpu_uuid


def test_get_all_active_cases(case_repo):
    """Tests retrieving all cases that are not in a terminal state."""
    # Add cases with various statuses
    case_repo.add_case("case_active_1", Path("/path/active1"))  # PENDING
    case_repo.add_case("case_active_2", Path("/path/active2"))
    case_repo.update_case_status("case_active_2", CaseStatus.PROCESSING)
    case_repo.add_case("case_terminal_1", Path("/path/terminal1"))
    case_repo.update_case_status("case_terminal_1", CaseStatus.COMPLETED)
    case_repo.add_case("case_terminal_2", Path("/path/terminal2"))
    case_repo.update_case_status("case_terminal_2", CaseStatus.FAILED)

    active_cases = case_repo.get_all_active_cases()
    assert len(active_cases) == 2
    active_case_ids = {c.case_id for c in active_cases}
    assert "case_active_1" in active_case_ids
    assert "case_active_2" in active_case_ids
    assert "case_terminal_1" not in active_case_ids
    assert "case_terminal_2" not in active_case_ids
