import pytest
from unittest.mock import MagicMock, call
from src.core.case_aggregator import update_case_status_from_beams
from src.domain.enums import CaseStatus, BeamStatus

@pytest.fixture
def mock_case_repo():
    return MagicMock()

def test_update_case_all_beams_completed(mock_case_repo):
    """Test that case status becomes COMPLETED when all beams are COMPLETED."""
    case_id = "case_all_completed"
    beams = [
        MagicMock(status=BeamStatus.COMPLETED),
        MagicMock(status=BeamStatus.COMPLETED),
    ]
    mock_case_repo.get_beams_for_case.return_value = beams

    update_case_status_from_beams(case_id, mock_case_repo)

    mock_case_repo.update_case_status.assert_called_once_with(
        case_id, CaseStatus.COMPLETED
    )

def test_update_case_one_beam_failed(mock_case_repo):
    """Test that case status becomes FAILED if any beam is FAILED."""
    case_id = "case_one_failed"
    beams = [
        MagicMock(status=BeamStatus.COMPLETED),
        MagicMock(status=BeamStatus.FAILED),
        MagicMock(status=BeamStatus.PENDING),
    ]
    mock_case_repo.get_beams_for_case.return_value = beams

    update_case_status_from_beams(case_id, mock_case_repo)

    mock_case_repo.update_case_status.assert_called_once_with(
        case_id, CaseStatus.FAILED, error_message="1 beam(s) failed."
    )

def test_update_case_still_processing(mock_case_repo):
    """Test that case status is PROCESSING if beams are not all finished."""
    case_id = "case_processing"
    beams = [
        MagicMock(status=BeamStatus.COMPLETED),
        MagicMock(status=BeamStatus.HPC_RUNNING),
        MagicMock(status=BeamStatus.PENDING),
    ]
    mock_case_repo.get_beams_for_case.return_value = beams

    update_case_status_from_beams(case_id, mock_case_repo)

    # Progress should be (1 completed / 3 total) * 100
    expected_progress = (1 / 3) * 100
    mock_case_repo.update_case_status.assert_called_once_with(
        case_id, CaseStatus.PROCESSING, progress=expected_progress
    )

def test_no_beams_does_nothing(mock_case_repo):
    """Test that nothing happens if a case has no beams."""
    case_id = "case_no_beams"
    mock_case_repo.get_beams_for_case.return_value = []

    update_case_status_from_beams(case_id, mock_case_repo)

    mock_case_repo.update_case_status.assert_not_called()
