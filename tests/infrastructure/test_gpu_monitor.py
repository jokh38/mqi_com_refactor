import pytest
from unittest.mock import MagicMock
import subprocess
from datetime import datetime

from src.infrastructure.gpu_monitor import GpuMonitor, GpuResourceError
from src.infrastructure.logging_handler import LoggerFactory, StructuredLogger
from src.config.settings import LoggingConfig

# Sample valid nvidia-smi output
VALID_NVIDIA_SMI_OUTPUT = """\
GPU-a3b9e8f7-c6d1-4e2a-9a0d-3f0e8d1c2b3a, NVIDIA GeForce RTX 3080, 10240, 1024, 9216, 65, 50
GPU-b4c0f9g8-d7e2-5f3b-0b1e-4g1f9e2d3c4b, NVIDIA GeForce RTX 3080, 10240, 2048, 8192, 70, 75
"""

# Sample malformed nvidia-smi output
MALFORMED_NVIDIA_SMI_OUTPUT = """\
GPU-a3b9e8f7-c6d1-4e2a-9a0d-3f0e8d1c2b3a, NVIDIA GeForce RTX 3080, 10240, 1024, 9216, 65, 50, extra_field
"""

# Sample output with invalid data types
INVALID_DATA_NVIDIA_SMI_OUTPUT = """\
GPU-a3b9e8f7-c6d1-4e2a-9a0d-3f0e8d1c2b3a, NVIDIA, invalid_mem, 1024, 9216, 65, 50
"""

@pytest.fixture(scope="module")
def logger():
    """Fixture to create a logger for tests."""
    log_config = LoggingConfig(log_level="DEBUG", structured_logging=False)
    LoggerFactory.configure(log_config)
    return LoggerFactory.get_logger("test_gpu_monitor")

@pytest.fixture
def gpu_monitor(logger: StructuredLogger) -> GpuMonitor:
    """Fixture to create a GpuMonitor instance."""
    return GpuMonitor(logger=logger, timeout=5)

def test_get_gpu_data_success(gpu_monitor: GpuMonitor, mocker):
    """Test successful retrieval and parsing of GPU data."""
    mock_run = mocker.patch('subprocess.run', return_value=MagicMock(stdout=VALID_NVIDIA_SMI_OUTPUT, check_returncode=None))

    gpu_data = gpu_monitor.get_gpu_data()

    assert len(gpu_data) == 2
    assert gpu_data[0]['uuid'] == 'GPU-a3b9e8f7-c6d1-4e2a-9a0d-3f0e8d1c2b3a'
    assert gpu_data[0]['memory_total'] == 10240
    assert gpu_data[1]['name'] == 'NVIDIA GeForce RTX 3080'
    assert gpu_data[1]['utilization'] == 75
    assert isinstance(gpu_data[0]['last_updated'], datetime)

    mock_run.assert_called_once()

def test_get_gpu_data_timeout(gpu_monitor: GpuMonitor, mocker):
    """Test GpuResourceError is raised on command timeout."""
    mocker.patch('subprocess.run', side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5))

    with pytest.raises(GpuResourceError, match="nvidia-smi command timed out"):
        gpu_monitor.get_gpu_data()

def test_get_gpu_data_command_failed(gpu_monitor: GpuMonitor, mocker):
    """Test GpuResourceError is raised on command failure."""
    mocker.patch('subprocess.run', side_effect=subprocess.CalledProcessError(returncode=1, cmd="nvidia-smi", stderr="mock error"))

    with pytest.raises(GpuResourceError, match="nvidia-smi command failed"):
        gpu_monitor.get_gpu_data()

def test_parse_malformed_output(gpu_monitor: GpuMonitor, mocker):
    """Test that malformed rows in nvidia-smi output are skipped."""
    mocker.patch('subprocess.run', return_value=MagicMock(stdout=MALFORMED_NVIDIA_SMI_OUTPUT))

    gpu_data = gpu_monitor.get_gpu_data()
    # The malformed row should be skipped, so the result is empty
    assert len(gpu_data) == 0

def test_parse_invalid_data_output(gpu_monitor: GpuMonitor, mocker):
    """Test that rows with invalid data types are skipped."""
    mocker.patch('subprocess.run', return_value=MagicMock(stdout=INVALID_DATA_NVIDIA_SMI_OUTPUT))

    gpu_data = gpu_monitor.get_gpu_data()
    # The row with invalid memory value should be skipped
    assert len(gpu_data) == 0

def test_check_nvidia_smi_available_success(gpu_monitor: GpuMonitor, mocker):
    """Test check_nvidia_smi_available returns True when command succeeds."""
    mocker.patch('subprocess.run', return_value=MagicMock(stdout="NVIDIA-SMI 510.47.03", check_returncode=None))

    assert gpu_monitor.check_nvidia_smi_available() is True

def test_check_nvidia_smi_available_failure(gpu_monitor: GpuMonitor, mocker):
    """Test check_nvidia_smi_available returns False when command fails."""
    mocker.patch('subprocess.run', side_effect=FileNotFoundError)

    assert gpu_monitor.check_nvidia_smi_available() is False

def test_private_parsers(gpu_monitor: GpuMonitor):
    """Test the private parsing helper methods."""
    assert gpu_monitor._parse_memory_value(" 1024 ") == 1024
    assert gpu_monitor._parse_temperature_value(" 65 ") == 65
    assert gpu_monitor._parse_utilization_value(" 50 ") == 50
    assert gpu_monitor._parse_memory_value("N/A") == 0

    with pytest.raises(ValueError):
        gpu_monitor._parse_memory_value("invalid")
=======
from unittest.mock import MagicMock, patch, call
import threading
import time

# Mock external dependencies before they are imported by the module under test
@pytest.fixture(autouse=True)
def mock_dependencies(mocker):
    mocker.patch('src.infrastructure.gpu_monitor.RemoteHandler')
    mocker.patch('src.infrastructure.gpu_monitor.GpuRepository')
    mocker.patch('src.infrastructure.gpu_monitor.StructuredLogger')

@pytest.fixture
def mock_remote_handler(mocker):
    handler = MagicMock()
    # Simulate a successful command execution
    success_result = MagicMock()
    success_result.success = True
    # A sample CSV line. Note the spaces to simulate real output.
    success_result.output = "gpu-uuid-1, NVIDIA RTX 3090, 24576, 1024, 23552, 65, 10"
    handler.execute_remote_command.return_value = success_result
    return handler

@pytest.fixture
def mock_gpu_repository(mocker):
    return MagicMock()

@pytest.fixture
def mock_logger(mocker):
    return MagicMock()

@pytest.fixture
def gpu_monitor(mock_logger, mock_remote_handler, mock_gpu_repository):
    from src.infrastructure.gpu_monitor import GpuMonitor
    # Use a short interval for testing
    monitor = GpuMonitor(
        logger=mock_logger,
        remote_handler=mock_remote_handler,
        gpu_repository=mock_gpu_repository,
        update_interval=0.1
    )
    return monitor

def test_gpu_monitor_initialization(gpu_monitor, mock_logger, mock_remote_handler, mock_gpu_repository):
    """Test that the GpuMonitor initializes correctly."""
    assert gpu_monitor.logger is mock_logger
    assert gpu_monitor.remote_handler is mock_remote_handler
    assert gpu_monitor.gpu_repository is mock_gpu_repository
    assert gpu_monitor.update_interval == 0.1
    assert gpu_monitor._monitor_thread is None
    assert isinstance(gpu_monitor._shutdown_event, threading.Event)

@patch('src.infrastructure.gpu_monitor.threading.Thread')
def test_start(mock_thread, gpu_monitor, mock_logger):
    """Test that start() creates and starts a background thread."""
    gpu_monitor.start()

    mock_thread.assert_called_once_with(target=gpu_monitor._monitor_loop, daemon=True)
    gpu_monitor._monitor_thread.start.assert_called_once()
    mock_logger.info.assert_called_with("Starting GPU monitoring service.")

def test_start_already_running(gpu_monitor, mock_logger):
    """Test that start() does nothing if the monitor is already running."""
    gpu_monitor._monitor_thread = MagicMock()
    gpu_monitor._monitor_thread.is_alive.return_value = True

    gpu_monitor.start()

    mock_logger.warning.assert_called_with("GPU monitor is already running.")

def test_stop(gpu_monitor, mock_logger):
    """Test that stop() sets the shutdown event and joins the thread."""
    mock_thread = MagicMock()
    gpu_monitor._monitor_thread = mock_thread
    mock_thread.is_alive.return_value = True

    gpu_monitor.stop()

    assert gpu_monitor._shutdown_event.is_set()
    mock_thread.join.assert_called_once_with(timeout=10)
    mock_logger.info.assert_called_with("Stopping GPU monitoring service.")

@patch('src.infrastructure.gpu_monitor.time.sleep', side_effect=InterruptedError) # To break loop
def test_monitor_loop_logic(mock_sleep, gpu_monitor, mock_remote_handler, mock_gpu_repository, mock_logger):
    """
    Test a single iteration of the monitor loop to verify its core logic.
    We use an exception to break out of the infinite loop for the test.
    """
    # This is a bit of a trick. We'll run the loop in a separate thread,
    # but the mocked sleep will raise an exception to stop it after one iteration.

    # Redefine the shutdown event's wait method to also raise the exception
    gpu_monitor._shutdown_event.wait = MagicMock(side_effect=InterruptedError)

    with pytest.raises(InterruptedError):
        gpu_monitor._monitor_loop()

    # Verify that the remote command was executed
    from src.config.constants import NVIDIA_SMI_QUERY_COMMAND
    mock_remote_handler.execute_remote_command.assert_called_once_with(
        case_id="gpu_monitoring",
        command=NVIDIA_SMI_QUERY_COMMAND
    )

    # Verify that the repository was updated with parsed data
    mock_gpu_repository.update_resources.assert_called_once()
    # Check the argument passed to update_resources
    call_args, _ = mock_gpu_repository.update_resources.call_args
    assert len(call_args[0]) == 1
    parsed_data = call_args[0][0]
    assert parsed_data['uuid'] == 'gpu-uuid-1'
    assert parsed_data['name'] == 'NVIDIA RTX 3090'
    assert parsed_data['memory_total'] == 24576

    # Verify that the shutdown event wait was called
    gpu_monitor._shutdown_event.wait.assert_called_once_with(gpu_monitor.update_interval)

def test_fetch_and_update_gpus_command_fails(gpu_monitor, mock_remote_handler, mock_gpu_repository, mock_logger):
    """Test the case where the remote command fails."""
    # Simulate a failed command execution
    failure_result = MagicMock()
    failure_result.success = False
    failure_result.error = "Connection failed"
    mock_remote_handler.execute_remote_command.return_value = failure_result

    gpu_monitor._fetch_and_update_gpus()

    # Verify an error was logged
    mock_logger.error.assert_called_with("Remote nvidia-smi command failed", {
        "return_code": failure_result.return_code,
        "error": "Connection failed"
    })

    # Verify the repository was not called
    mock_gpu_repository.update_resources.assert_not_called()

