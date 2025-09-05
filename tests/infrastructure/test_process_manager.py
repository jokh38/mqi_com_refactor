import pytest
import subprocess
from unittest.mock import MagicMock
from pathlib import Path
from concurrent.futures import Future

from src.infrastructure.process_manager import ProcessManager, CommandExecutor, ProcessingError
from src.config.settings import ProcessingConfig
from src.infrastructure.logging_handler import LoggerFactory, LoggingConfig

@pytest.fixture(scope="module")
def logger():
    log_config = LoggingConfig(log_level="DEBUG")
    LoggerFactory.configure(log_config)
    return LoggerFactory.get_logger("test_process_manager")

@pytest.fixture
def command_executor(logger):
    return CommandExecutor(logger=logger, default_timeout=10)

@pytest.fixture
def processing_config():
    return ProcessingConfig(max_workers=4)

# --- Tests for CommandExecutor ---

def test_execute_command_success(command_executor, mocker):
    """Test successful command execution."""
    mock_run = mocker.patch('subprocess.run', return_value=MagicMock(
        returncode=0, stdout="Success", stderr=""
    ))

    command = ["echo", "hello"]
    result = command_executor.execute_command(command)

    mock_run.assert_called_once_with(
        command,
        cwd=None,
        timeout=10,
        capture_output=True,
        text=True,
        env=None,
        check=True
    )
    assert result.returncode == 0
    assert result.stdout == "Success"

def test_execute_command_timeout(command_executor, mocker):
    """Test that ProcessingError is raised on command timeout."""
    mocker.patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="sleep 15", timeout=10))

    with pytest.raises(ProcessingError, match="Command timed out"):
        command_executor.execute_command(["sleep", "15"])

def test_execute_command_failure(command_executor, mocker):
    """Test that ProcessingError is raised on command failure."""
    mocker.patch('subprocess.run', side_effect=subprocess.CalledProcessError(
        returncode=1, cmd="ls /nonexistent", stderr="No such file or directory"
    ))

    with pytest.raises(ProcessingError, match="Command failed with code 1"):
        command_executor.execute_command(["ls", "/nonexistent"])

def test_execute_command_async(command_executor, mocker):
    """Test asynchronous command execution."""
    mock_popen = mocker.patch('subprocess.Popen')

    command = ["./run_script.sh"]
    command_executor.execute_command_async(command)

    mock_popen.assert_called_once_with(
        command,
        cwd=None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=None
    )

# --- Tests for ProcessManager ---

@pytest.fixture
def process_manager(processing_config, logger):
    """Fixture to create a ProcessManager instance."""
    pm = ProcessManager(config=processing_config, logger=logger)
    return pm

def dummy_worker_func(case_id, case_path):
    """A dummy function for testing process submission."""
    return f"Processed {case_id}"

def test_process_manager_start_and_shutdown(process_manager, mocker):
    """Test starting and shutting down the process manager."""
    mock_pool_executor = MagicMock()
    mocker.patch('src.infrastructure.process_manager.ProcessPoolExecutor', return_value=mock_pool_executor)

    assert process_manager._executor is None

    process_manager.start()
    assert process_manager._executor is mock_pool_executor

    process_manager.shutdown(wait=True)
    mock_pool_executor.shutdown.assert_called_once_with(wait=True)
    assert process_manager._executor is None

def test_submit_case_processing(process_manager, mocker):
    """Test submitting a case for processing."""
    mock_pool_executor = MagicMock()
    mocker.patch('src.infrastructure.process_manager.ProcessPoolExecutor', return_value=mock_pool_executor)

    process_manager.start()

    # Mock the future object that submit returns
    mock_future = Future()
    mock_pool_executor.submit.return_value = mock_future

    case_id = "case123"
    case_path = Path("/tmp/case123")

    process_id = process_manager.submit_case_processing(dummy_worker_func, case_id, case_path)

    assert process_id.startswith(f"case_{case_id}")
    mock_pool_executor.submit.assert_called_once_with(dummy_worker_func, case_id, case_path)
    assert process_manager.get_active_process_count() == 1

    # Check that the completion callback was added
    assert len(mock_future._done_callbacks) == 1

def test_process_completion_callback_success(process_manager, mocker):
    """Test the callback for a successfully completed process."""
    mocker.patch('src.infrastructure.process_manager.ProcessPoolExecutor') # We need to start the manager
    process_manager.start()

    # Manually call the private callback method for testing
    mock_future = Future()
    mock_future.set_result("Success!")

    process_manager._active_processes['proc1'] = mock_future

    process_manager._process_completed('proc1', mock_future)

    assert process_manager.get_active_process_count() == 0

def test_process_completion_callback_failure(process_manager, mocker):
    """Test the callback for a failed process."""
    mocker.patch('src.infrastructure.process_manager.ProcessPoolExecutor') # We need to start the manager
    process_manager.start()

    mock_future = Future()
    mock_future.set_exception(ValueError("Something went wrong"))

    process_manager._active_processes['proc1'] = mock_future

    process_manager._process_completed('proc1', mock_future)

    assert process_manager.get_active_process_count() == 0

def test_submit_to_stopped_manager_raises_error(process_manager, mocker):
    """Test that submitting a task to a stopped manager raises a RuntimeError."""
    with pytest.raises(RuntimeError, match="Process manager not started"):
        process_manager.submit_case_processing(dummy_worker_func, "case1", Path("/tmp"))

    # We need to mock the executor to test the shutdown logic
    mock_pool_executor = MagicMock()
    mocker.patch('src.infrastructure.process_manager.ProcessPoolExecutor', return_value=mock_pool_executor)
    process_manager.start()
    process_manager.shutdown(wait=False)

    with pytest.raises(RuntimeError, match="Process manager not started"):
        process_manager.submit_case_processing(dummy_worker_func, "case2", Path("/tmp"))
