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
