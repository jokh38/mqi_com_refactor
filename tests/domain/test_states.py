import pytest
from unittest.mock import Mock, MagicMock, patch, call
from pathlib import Path

from src.domain.states import (
    InitialState,
    FileUploadState,
    HpcExecutionState,
    DownloadState,
    PostprocessingState,
    CompletedState,
    FailedState,
)
from src.domain.enums import CaseStatus


@pytest.fixture
def mock_context():
    """
    Provides a mocked WorkflowManager context object for state tests.
    Now represents a beam worker context.
    """
    context = MagicMock()
    context.id = "test-case-001_beam_1"
    context.path = MagicMock(spec=Path)
    context.path.__str__.return_value = f"/tmp/{context.id}"
    context.path.__truediv__.return_value = MagicMock(spec=Path)

    # Mock dependencies
    context.logger = MagicMock()
    context.case_repo = MagicMock()
    context.gpu_repo = MagicMock()
    context.local_handler = MagicMock()
    context.remote_handler = MagicMock()
    context.tps_generator = MagicMock()
    context.shared_context = {}

    # Mock the beam object that would be in the DB
    mock_beam = MagicMock()
    mock_beam.parent_case_id = "test-case-001"
    mock_beam.beam_id = context.id
    context.case_repo.get_beam.return_value = mock_beam

    return context


# --- Tests for InitialState ---

def test_initial_state_success(mock_context):
    from src.domain.enums import BeamStatus
    state = InitialState()
    mock_context.path.is_dir.return_value = True
    mock_context.gpu_repo.find_and_lock_available_gpu.return_value = {'gpu_uuid': 'gpu-1'}
    mock_context.tps_generator.generate_tps_file.return_value = True
    (mock_context.path / "moqui_tps.in").exists.return_value = True


    next_state = state.execute(mock_context)

    mock_context.case_repo.update_beam_status.assert_called_once_with(
        mock_context.id, BeamStatus.PREPROCESSING
    )
    assert isinstance(next_state, FileUploadState)


def test_initial_state_path_is_not_dir(mock_context):
    from src.domain.enums import BeamStatus
    state = InitialState()
    mock_context.path.is_dir.return_value = False

    next_state = state.execute(mock_context)

    original_error = f"Beam path is not a valid directory: {mock_context.path}"
    expected_error = f"Error in state '{state.get_state_name()}' for beam '{mock_context.id}': {original_error}"
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED, error_message=expected_error
    )
    assert isinstance(next_state, FailedState)


def test_initial_state_get_name():
    assert InitialState().get_state_name() == "Initial Validation"


# --- Tests for FileUploadState ---

def test_file_upload_state_success(mock_context):
    from src.domain.enums import BeamStatus
    state = FileUploadState()

    # Mock the paths and files
    mock_context.path.glob.return_value = [Path("file1.csv"), Path("file2.csv")]
    (mock_context.path / "moqui_tps.in").exists.return_value = True

    # Mock settings and successful upload
    mock_context.local_handler.settings.get_hpc_paths.return_value = {"remote_case_path_template": "/remote/cases"}
    mock_context.remote_handler.upload_file.return_value = Mock(success=True)

    next_state = state.execute(mock_context)

    # Should be called for each csv file + the tps file
    assert mock_context.remote_handler.upload_file.call_count == 3
    mock_context.case_repo.update_beam_status.assert_called_once_with(
        mock_context.id, BeamStatus.UPLOADING
    )
    assert isinstance(next_state, HpcExecutionState)
    assert "remote_beam_dir" in mock_context.shared_context


def test_file_upload_state_upload_fails(mock_context):
    from src.domain.enums import BeamStatus
    state = FileUploadState()

    # Mock paths and files
    mock_context.path.glob.return_value = [Path("file1.csv")]
    (mock_context.path / "moqui_tps.in").exists.return_value = True
    mock_context.local_handler.settings.get_hpc_paths.return_value = {"remote_case_path_template": "/remote/cases"}

    # Mock a failed upload
    original_error = "Failed to upload file file1.csv: Permission denied"
    mock_context.remote_handler.upload_file.return_value = Mock(success=False, error="Permission denied")

    next_state = state.execute(mock_context)

    expected_error = f"Error in state '{state.get_state_name()}' for beam '{mock_context.id}': {original_error}"
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED, error_message=expected_error
    )
    assert isinstance(next_state, FailedState)


def test_file_upload_state_get_name():
    assert FileUploadState().get_state_name() == "File Upload"


# --- Tests for CompletedState ---

def test_completed_state_execution(mock_context):
    from src.domain.enums import BeamStatus
    state = CompletedState()
    next_state = state.execute(mock_context)
    mock_context.case_repo.update_beam_status.assert_called_once_with(
        mock_context.id, BeamStatus.COMPLETED
    )
    assert next_state is None


def test_completed_state_get_name():
    assert CompletedState().get_state_name() == "Completed"


# --- Tests for FailedState ---

def test_failed_state_execution(mock_context):
    from src.domain.enums import BeamStatus
    state = FailedState()
    next_state = state.execute(mock_context)
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED
    )
    mock_context.gpu_repo.release_all_for_case.assert_called_once_with(
        mock_context.id
    )
    assert next_state is None


def test_failed_state_get_name():
    assert FailedState().get_state_name() == "Failed"


# --- Tests for HpcExecutionState ---

def test_hpc_execution_state_success(mock_context):
    from src.domain.enums import BeamStatus
    state = HpcExecutionState()
    mock_gpu_alloc = {'gpu_uuid': "gpu-test-1"}
    mock_context.gpu_repo.find_and_lock_available_gpu.return_value = mock_gpu_alloc
    mock_context.remote_handler.submit_simulation_job.return_value = Mock(
        success=True, job_id="job-123"
    )
    mock_context.remote_handler.wait_for_job_completion.return_value = Mock(
        failed=False
    )
    mock_context.shared_context["remote_beam_dir"] = "/remote/beam/dir"

    next_state = state.execute(mock_context)

    mock_context.case_repo.assign_hpc_job_id_to_beam.assert_called_once_with(mock_context.id, "job-123")
    mock_context.case_repo.update_beam_status.assert_has_calls([
        call(mock_context.id, BeamStatus.HPC_QUEUED),
        call(mock_context.id, BeamStatus.HPC_RUNNING),
    ])
    mock_context.gpu_repo.release_gpu.assert_called_once_with("gpu-test-1")
    assert isinstance(next_state, DownloadState)


def test_hpc_execution_state_no_gpu(mock_context):
    from src.domain.enums import BeamStatus
    state = HpcExecutionState()
    mock_context.gpu_repo.find_and_lock_available_gpu.return_value = None

    next_state = state.execute(mock_context)

    original_error = "No GPU available for simulation"
    expected_error = f"Error in state '{state.get_state_name()}' for beam '{mock_context.id}': {original_error}"
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED, error_message=expected_error
    )
    assert isinstance(next_state, FailedState)


# --- Tests for DownloadState ---

def test_download_state_success(mock_context):
    from src.domain.enums import BeamStatus
    state = DownloadState()
    mock_context.remote_handler.download_file.return_value = Mock(success=True)
    mock_context.shared_context["remote_beam_dir"] = "/remote/beam/dir"

    # Mock path setup
    mock_local_result_dir = MagicMock(spec=Path)
    mock_context.local_handler.settings.get_case_directories.return_value = {"final_dicom": "/results/{case_id}"}
    with patch('src.domain.states.Path', return_value=mock_local_result_dir):
        (mock_local_result_dir / mock_context.id / "output.raw").exists.return_value = True
        next_state = state.execute(mock_context)

    mock_context.remote_handler.cleanup_remote_directory.assert_called_once_with("/remote/beam/dir")
    assert isinstance(next_state, PostprocessingState)
    assert "raw_output_file" in mock_context.shared_context


def test_download_state_main_file_missing(mock_context):
    from src.domain.enums import BeamStatus
    state = DownloadState()
    mock_context.remote_handler.download_file.return_value = Mock(success=True)
    mock_context.shared_context["remote_beam_dir"] = "/remote/beam/dir"

    # Mock path setup
    mock_local_result_dir = MagicMock(spec=Path)
    mock_context.local_handler.settings.get_case_directories.return_value = {"final_dicom": "/results/{case_id}"}
    with patch('src.domain.states.Path', return_value=mock_local_result_dir):
        (mock_local_result_dir / mock_context.id / "output.raw").exists.return_value = False
        next_state = state.execute(mock_context)

    original_error = "Main output file 'output.raw' was not downloaded."
    expected_error = f"Error in state '{state.get_state_name()}' for beam '{mock_context.id}': {original_error}"
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED, error_message=expected_error
    )
    assert isinstance(next_state, FailedState)


# --- Tests for PostprocessingState ---

def test_postprocessing_state_success(mock_context):
    from src.domain.enums import BeamStatus
    state = PostprocessingState()

    mock_raw_file = MagicMock(spec=Path)
    mock_raw_file.exists.return_value = True
    mock_dcm_dir = MagicMock(spec=Path)
    mock_dcm_dir.glob.return_value = ["file.dcm"]
    mock_raw_file.parent.__truediv__.return_value = mock_dcm_dir

    mock_context.shared_context["raw_output_file"] = mock_raw_file
    mock_context.local_handler.run_raw_to_dcm.return_value = Mock(success=True)

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_beam_status.assert_called_once_with(mock_context.id, BeamStatus.POSTPROCESSING)
    mock_context.local_handler.run_raw_to_dcm.assert_called_once_with(
        input_file=mock_raw_file,
        output_dir=mock_dcm_dir,
        case_path=mock_context.path
    )
    mock_raw_file.unlink.assert_called_once()
    assert isinstance(next_state, CompletedState)


def test_postprocessing_state_dcm_fails(mock_context):
    from src.domain.enums import BeamStatus
    state = PostprocessingState()

    mock_raw_file = MagicMock(spec=Path)
    mock_raw_file.exists.return_value = True
    mock_context.shared_context["raw_output_file"] = mock_raw_file
    original_error = f"RawToDCM failed for beam {mock_context.id}: DCM conversion failed"
    mock_context.local_handler.run_raw_to_dcm.return_value = Mock(success=False, error="DCM conversion failed")

    next_state = state.execute(mock_context)

    expected_error = f"Error in state '{state.get_state_name()}' for beam '{mock_context.id}': {original_error}"
    mock_context.case_repo.update_beam_status.assert_called_with(
        mock_context.id, BeamStatus.FAILED, error_message=expected_error
    )
    assert isinstance(next_state, FailedState)
