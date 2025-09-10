import pytest
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
        command="nvidia-smi --query-gpu=uuid,name,memory.total,memory.used,memory.free,temperature.gpu,utilization.gpu --format=csv,noheader,nounits",
        update_interval=0.1
    )
    return monitor

def test_gpu_monitor_initialization(gpu_monitor, mock_logger, mock_remote_handler, mock_gpu_repository):
    """Test that the GpuMonitor initializes correctly."""
    assert gpu_monitor.logger is mock_logger
    assert gpu_monitor.remote_handler is mock_remote_handler
    assert gpu_monitor.gpu_repository is mock_gpu_repository
    assert gpu_monitor.update_interval == 0.1
    assert gpu_monitor.command is not None
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
    mock_remote_handler.execute_remote_command.assert_called_once_with(
        context_id="gpu_monitoring",
        command=gpu_monitor.command
    )

    # Verify that the repository was updated with parsed data
    mock_gpu_repository.update_resources.assert_called_once()
    # Check the argument passed to update_resources
    call_args, _ = mock_gpu_repository.update_resources.call_args
    assert len(call_args[0]) == 1
    parsed_data = call_args[0][0]
    assert parsed_data['uuid'] == 'gpu-uuid-1'
    assert parsed_data['name'] == 'RTX 3090'
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

def test_parse_gpu_name(gpu_monitor):
    """Test the _parse_gpu_name method."""
    assert gpu_monitor._parse_gpu_name("  NVIDIA RTX 3090  ") == "RTX 3090"
    assert gpu_monitor._parse_gpu_name("RTX 3090") == "RTX 3090"
    assert gpu_monitor._parse_gpu_name("NVIDIA Tesla V100") == "Tesla V100"
    assert gpu_monitor._parse_gpu_name("  AMD Radeon Pro WX 7100  ") == "AMD Radeon Pro WX 7100"
    assert gpu_monitor._parse_gpu_name("") == ""
