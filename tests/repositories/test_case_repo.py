import pytest
from pathlib import Path
from src.repositories.case_repo import CaseRepository
from src.domain.enums import CaseStatus, BeamStatus, WorkflowStep
from src.domain.models import CaseData, BeamData

@pytest.fixture
def case_repo(db_connection, logger):
    """Pytest fixture for creating a CaseRepository instance."""
    return CaseRepository(db_connection, logger)

def test_add_case(case_repo, db_connection):
    """Tests that a new case can be added to the database."""
    case_id = "case_001"
    case_path = Path("/path/to/case_001")
    case_repo.add_case(case_id, case_path)

    with db_connection.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        assert row is not None
        assert row["case_id"] == case_id
        assert row["case_path"] == str(case_path)
        assert row["status"] == CaseStatus.PENDING.value

def test_update_case_status(case_repo):
    """Tests updating the status and progress of a case."""
    case_id = "case_002"
    case_repo.add_case(case_id, Path("/path/to/case_002"))
    case_repo.update_case_status(case_id, CaseStatus.PROCESSING, progress=50.0)
    case = case_repo.get_case(case_id)
    assert case.status == CaseStatus.PROCESSING and case.progress == 50.0

def test_get_case(case_repo):
    """Tests retrieving a single case by its ID."""
    case_id = "case_003"
    case_repo.add_case(case_id, Path("/path/to/case_003"))
    case = case_repo.get_case(case_id)
    assert isinstance(case, CaseData) and case.case_id == case_id

def test_get_all_case_ids(case_repo):
    """Tests retrieving all case IDs."""
    case_repo.add_case("case_id_1", Path("/path/1"))
    case_repo.add_case("case_id_2", Path("/path/2"))
    ids = case_repo.get_all_case_ids()
    assert len(ids) == 2 and "case_id_1" in ids

def test_record_and_get_workflow_steps(case_repo):
    """Tests recording and retrieving workflow steps."""
    case_id = "case_workflow_001"
    case_repo.add_case(case_id, Path("/path/workflow1"))
    case_repo.record_workflow_step(case_id, WorkflowStep.PREPROCESSING, "started")
    steps = case_repo.get_workflow_steps(case_id)
    assert len(steps) == 1 and steps[0].step == WorkflowStep.PREPROCESSING

def test_assign_gpu_to_case(case_repo):
    """Tests assigning a GPU to a case."""
    case_id = "case_gpu_assign_001"
    gpu_uuid = "GPU-12345"
    case_repo.add_case(case_id, Path("/path/gpu_case"))
    case_repo.assign_gpu_to_case(case_id, gpu_uuid)
    case = case_repo.get_case(case_id)
    assert case.assigned_gpu == gpu_uuid

def test_get_all_active_cases(case_repo):
    """Tests retrieving all active cases."""
    case_repo.add_case("case_active_1", Path("/path/active1"))
    case_repo.update_case_status("case_active_1", CaseStatus.PROCESSING)
    case_repo.add_case("case_terminal_1", Path("/path/terminal1"))
    case_repo.update_case_status("case_terminal_1", CaseStatus.COMPLETED)
    active_cases = case_repo.get_all_active_cases()
    assert len(active_cases) == 1 and active_cases[0].case_id == "case_active_1"

# --- Beam Method Tests ---

def test_create_beam_record(case_repo):
    """Tests that a new beam record can be added."""
    case_id = "parent_case_01"
    beam_id = f"{case_id}_beam1"
    beam_path = Path(f"/path/to/{case_id}/beam1")
    case_repo.add_case(case_id, Path(f"/path/to/{case_id}"))

    case_repo.create_beam_record(beam_id, case_id, beam_path)

    beam = case_repo.get_beam(beam_id)
    assert beam is not None
    assert beam.beam_id == beam_id
    assert beam.parent_case_id == case_id
    assert beam.status == BeamStatus.PENDING

def test_update_beam_status(case_repo):
    """Tests updating the status of a beam."""
    case_id = "parent_case_02"
    beam_id = f"{case_id}_beam1"
    case_repo.add_case(case_id, Path(f"/path/to/{case_id}"))
    case_repo.create_beam_record(beam_id, case_id, Path(f"/path/to/{case_id}/beam1"))

    case_repo.update_beam_status(beam_id, BeamStatus.HPC_RUNNING)
    beam = case_repo.get_beam(beam_id)
    assert beam.status == BeamStatus.HPC_RUNNING

def test_get_beams_for_case(case_repo):
    """Tests retrieving all beams for a given parent case."""
    case_id = "parent_case_03"
    case_repo.add_case(case_id, Path(f"/path/to/{case_id}"))

    case_repo.create_beam_record(f"{case_id}_beam1", case_id, Path(f"/path/to/{case_id}/beam1"))
    case_repo.create_beam_record(f"{case_id}_beam2", case_id, Path(f"/path/to/{case_id}/beam2"))

    beams = case_repo.get_beams_for_case(case_id)
    assert len(beams) == 2
    assert beams[0].beam_id == f"{case_id}_beam1"

def test_assign_hpc_job_id_to_beam(case_repo):
    """Tests assigning an HPC job ID to a beam."""
    case_id = "parent_case_04"
    beam_id = f"{case_id}_beam1"
    hpc_job_id = "12345"
    case_repo.add_case(case_id, Path(f"/path/to/{case_id}"))
    case_repo.create_beam_record(beam_id, case_id, Path(f"/path/to/{case_id}/beam1"))

    case_repo.assign_hpc_job_id_to_beam(beam_id, hpc_job_id)

    beam = case_repo.get_beam(beam_id)
    assert beam.hpc_job_id == hpc_job_id
