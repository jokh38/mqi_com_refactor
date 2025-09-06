import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from src.domain.states import (
    InitialState,
    PreprocessingState,
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
    """
    context = MagicMock()
    context.case_id = "test-case-001"

    context.case_path = MagicMock(spec=Path)
    context.case_path.__str__.return_value = f"/tmp/{context.case_id}"

    # This allows mocking of chained calls like `path / 'file'`
    context.case_path.__truediv__.return_value = MagicMock(spec=Path)

    # Mock dependencies
    context.logger = MagicMock()
    context.case_repo = MagicMock()
    context.gpu_repo = MagicMock()
    context.local_handler = MagicMock()
    context.remote_handler = MagicMock()

    return context


# --- Tests for InitialState ---

def test_initial_state_success(mock_context):
    state = InitialState()
    mock_context.case_path.is_dir.return_value = True
    mock_context.case_path.__truediv__.return_value.exists.return_value = True

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.PREPROCESSING
    )
    assert isinstance(next_state, PreprocessingState)


def test_initial_state_file_not_found(mock_context):
    state = InitialState()
    mock_context.case_path.is_dir.return_value = True
    mock_context.case_path.__truediv__.return_value.exists.return_value = False

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


def test_initial_state_path_is_not_dir(mock_context):
    state = InitialState()
    mock_context.case_path.is_dir.return_value = False

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


def test_initial_state_get_name():
    assert InitialState().get_state_name() == "Initial Validation"


# --- Tests for PreprocessingState ---

def test_preprocessing_state_success(mock_context):
    state = PreprocessingState()
    
    # Mock beam directories
    mock_beam1 = Mock()
    mock_beam1.is_dir.return_value = True
    mock_beam1.name = "beam1"
    mock_beam2 = Mock()
    mock_beam2.is_dir.return_value = True
    mock_beam2.name = "beam2"
    
    mock_context.case_path.iterdir.return_value = [mock_beam1, mock_beam2]
    
    # Mock moqui_tps.in file exists
    (mock_context.case_path / "moqui_tps.in").exists.return_value = True
    
    # Mock local handler settings
    mock_context.local_handler.settings.get_case_directories.return_value = {
        'processing': '/fake/processing/{case_id}'
    }
    mock_context.local_handler.settings.get_base_directory.return_value = '/fake/base'
    
    # Mock processing directory path and CSV files
    mock_processing_path = Mock()
    mock_processing_path.mkdir = Mock()
    mock_processing_path.glob.return_value = ['file1.csv', 'file2.csv']
    
    with patch('src.domain.states.Path', return_value=mock_processing_path):
        # Mock successful interpreter runs
        mock_context.local_handler.run_mqi_interpreter.return_value = Mock(success=True)
        
        next_state = state.execute(mock_context)

    assert isinstance(next_state, FileUploadState)


def test_preprocessing_state_interpreter_fails(mock_context):
    state = PreprocessingState()
    
    # Mock beam directories
    mock_beam1 = Mock()
    mock_beam1.is_dir.return_value = True
    mock_beam1.name = "beam1"
    
    mock_context.case_path.iterdir.return_value = [mock_beam1]
    
    # Mock moqui_tps.in file exists
    (mock_context.case_path / "moqui_tps.in").exists.return_value = True
    
    # Mock local handler settings
    mock_context.local_handler.settings.get_case_directories.return_value = {
        'processing': '/fake/processing/{case_id}'
    }
    mock_context.local_handler.settings.get_base_directory.return_value = '/fake/base'
    
    # Mock processing directory path
    mock_processing_path = Mock()
    mock_processing_path.mkdir = Mock()
    
    with patch('src.domain.states.Path', return_value=mock_processing_path):
        # Mock failed interpreter run
        mock_context.local_handler.run_mqi_interpreter.return_value = Mock(
            success=False, error="Interpreter failed"
        )
        
        next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


def test_preprocessing_state_get_name():
    assert PreprocessingState().get_state_name() == "Preprocessing"


# --- Tests for FileUploadState ---

def test_file_upload_state_success(mock_context):
    state = FileUploadState()
    mock_context.remote_handler.upload_file.return_value = Mock(success=True)
    mock_context.case_path.__truediv__.return_value.exists.return_value = True

    next_state = state.execute(mock_context)

    assert mock_context.remote_handler.upload_file.call_count == 3
    assert isinstance(next_state, HpcExecutionState)


def test_file_upload_state_upload_fails(mock_context):
    state = FileUploadState()
    mock_context.remote_handler.upload_file.return_value = Mock(success=False)
    mock_context.case_path.__truediv__.return_value.exists.return_value = True

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


def test_file_upload_state_get_name():
    assert FileUploadState().get_state_name() == "File Upload"


# --- Tests for CompletedState ---

def test_completed_state_execution(mock_context):
    state = CompletedState()
    next_state = state.execute(mock_context)
    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.COMPLETED
    )
    assert next_state is None


def test_completed_state_get_name():
    assert CompletedState().get_state_name() == "Completed"


# --- Tests for FailedState ---

def test_failed_state_execution(mock_context):
    state = FailedState()
    next_state = state.execute(mock_context)
    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    mock_context.gpu_repo.release_all_for_case.assert_called_once_with(
        mock_context.case_id
    )
    assert next_state is None


def test_failed_state_get_name():
    assert FailedState().get_state_name() == "Failed"


# --- Tests for HpcExecutionState ---

def test_hpc_execution_state_success(mock_context):
    state = HpcExecutionState()
    mock_gpu_alloc = Mock(gpu_uuid="gpu-test-1")
    mock_context.gpu_repo.find_and_lock_available_gpu.return_value = mock_gpu_alloc
    mock_context.remote_handler.submit_simulation_job.return_value = Mock(
        success=True, job_id="job-123"
    )
    mock_context.remote_handler.wait_for_job_completion.return_value = Mock(
        failed=False
    )

    next_state = state.execute(mock_context)

    mock_context.gpu_repo.release_gpu.assert_called_once_with(
        mock_gpu_alloc.gpu_uuid
    )
    assert isinstance(next_state, DownloadState)


def test_hpc_execution_state_no_gpu(mock_context):
    state = HpcExecutionState()
    mock_context.gpu_repo.find_and_lock_available_gpu.return_value = None

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


# --- Tests for DownloadState ---

def test_download_state_success(mock_context):
    state = DownloadState()
    mock_context.remote_handler.download_file.return_value = Mock(success=True)
    (mock_context.case_path / "output.raw").exists.return_value = True

    next_state = state.execute(mock_context)

    mock_context.remote_handler.cleanup_remote_directory.assert_called_once()
    assert isinstance(next_state, PostprocessingState)


def test_download_state_main_file_missing(mock_context):
    state = DownloadState()
    mock_context.remote_handler.download_file.return_value = Mock(success=True)
    (mock_context.case_path / "output.raw").exists.return_value = False

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_once_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)


# --- Tests for PostprocessingState ---

def test_postprocessing_state_success(mock_context):
    """
    Tests PostprocessingState success scenario with robust path mocking.
    """
    state = PostprocessingState()
    mock_context.local_handler.run_raw_to_dcm.return_value = Mock(success=True)

    mock_paths = {
        "output.raw": MagicMock(spec=Path, name="RawPath"),
        "dcm_output": MagicMock(spec=Path, name="DcmPath"),
        "preprocessed.json": MagicMock(spec=Path, name="PrepPath"),
        "simulation.log": MagicMock(spec=Path, name="LogPath")
    }
    mock_paths["dcm_output"].glob.return_value = ["file1.dcm"]
    mock_paths["preprocessed.json"].exists.return_value = True
    mock_paths["output.raw"].exists.return_value = True
    mock_paths["simulation.log"].exists.return_value = False

    def truediv_side_effect(filename):
        return mock_paths.get(filename, MagicMock())

    mock_context.case_path.__truediv__.side_effect = truediv_side_effect

    next_state = state.execute(mock_context)

    mock_paths["dcm_output"].mkdir.assert_called_once_with(exist_ok=True)
    mock_context.local_handler.run_raw_to_dcm.assert_called_once_with(
        input_file=mock_paths["output.raw"],
        output_dir=mock_paths["dcm_output"],
        case_path=mock_context.case_path
    )
    mock_paths["preprocessed.json"].unlink.assert_called_once()
    mock_paths["output.raw"].unlink.assert_called_once()
    mock_paths["simulation.log"].unlink.assert_not_called()
    assert isinstance(next_state, CompletedState)


def test_postprocessing_state_no_dcm_files(mock_context):
    state = PostprocessingState()
    mock_context.local_handler.run_raw_to_dcm.return_value = Mock(success=True)
    (mock_context.case_path / "dcm_output").glob.return_value = []

    next_state = state.execute(mock_context)

    mock_context.case_repo.update_case_status.assert_called_with(
        mock_context.case_id, CaseStatus.FAILED
    )
    assert isinstance(next_state, FailedState)
