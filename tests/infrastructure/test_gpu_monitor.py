import pytest
from unittest.mock import MagicMock, patch
import subprocess

from src.infrastructure.gpu_monitor import GpuMonitor
from src.domain.errors import GpuResourceError

@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    return MagicMock()

@pytest.fixture
def gpu_monitor(mock_logger):
    """Fixture for a GpuMonitor instance."""
    return GpuMonitor(logger=mock_logger)

# Sample nvidia-smi output
VALID_NVIDIA_SMI_OUTPUT = (
    "GPU-b6e6c4f9-of-a-kind, NVIDIA GeForce RTX 3080, 10240, 2048, 8192, 60, 50\n"
    "GPU-a1b2c3d4-of-another, NVIDIA GeForce RTX 3090, 24576, 4096, 20480, 65, 75\n"
)

MALFORMED_NVIDIA_SMI_OUTPUT = (
    "GPU-b6e6c4f9-of-a-kind, NVIDIA GeForce RTX 3080, 10240, 2048, 8192, 60\n" # Missing a column
)

INVALID_DATA_NVIDIA_SMI_OUTPUT = (
    "GPU-b6e6c4f9-of-a-kind, NVIDIA GeForce RTX 3080, 10240, 2048, 8192, not_a_temp, 50\n"
)

class TestGpuMonitor:
    @patch("subprocess.run")
    def test_get_gpu_data_success(self, mock_subprocess_run, gpu_monitor):
        """Test successful retrieval and parsing of GPU data."""
        mock_process = MagicMock()
        mock_process.stdout = VALID_NVIDIA_SMI_OUTPUT
        mock_subprocess_run.return_value = mock_process

        gpu_data = gpu_monitor.get_gpu_data()

        assert len(gpu_data) == 2
        assert gpu_data[0]['uuid'] == "GPU-b6e6c4f9-of-a-kind"
        assert gpu_data[0]['memory_total'] == 10240
        assert gpu_data[1]['name'] == "NVIDIA GeForce RTX 3090"
        mock_subprocess_run.assert_called_once()

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=10))
    def test_get_gpu_data_timeout(self, mock_subprocess_run, gpu_monitor):
        """Test that a timeout raises GpuResourceError."""
        with pytest.raises(GpuResourceError, match="timed out"):
            gpu_monitor.get_gpu_data()

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(returncode=1, cmd="nvidia-smi", stderr="error"))
    def test_get_gpu_data_command_error(self, mock_subprocess_run, gpu_monitor):
        """Test that a command error raises GpuResourceError."""
        with pytest.raises(GpuResourceError, match="failed"):
            gpu_monitor.get_gpu_data()

    @patch("subprocess.run")
    def test_parse_malformed_output(self, mock_subprocess_run, gpu_monitor, mock_logger):
        """Test that malformed CSV rows are skipped."""
        mock_process = MagicMock()
        mock_process.stdout = MALFORMED_NVIDIA_SMI_OUTPUT
        mock_subprocess_run.return_value = mock_process

        gpu_data = gpu_monitor.get_gpu_data()
        assert len(gpu_data) == 0
        mock_logger.warning.assert_called_with("Unexpected nvidia-smi output format", {
            "row_index": 0,
            "row_length": 6,
            "expected_length": 7,
            "row_data": ['GPU-b6e6c4f9-of-a-kind', ' NVIDIA GeForce RTX 3080', ' 10240', ' 2048', ' 8192', ' 60']
        })

    @patch("subprocess.run")
    def test_parse_invalid_data(self, mock_subprocess_run, gpu_monitor, mock_logger):
        """Test that rows with invalid data are skipped."""
        mock_process = MagicMock()
        mock_process.stdout = INVALID_DATA_NVIDIA_SMI_OUTPUT
        mock_subprocess_run.return_value = mock_process

        gpu_data = gpu_monitor.get_gpu_data()
        assert len(gpu_data) == 0
        mock_logger.warning.assert_called_with("Failed to parse GPU row", {
            "row_index": 0,
            "row_data": ['GPU-b6e6c4f9-of-a-kind', ' NVIDIA GeForce RTX 3080', ' 10240', ' 2048', ' 8192', ' not_a_temp', ' 50'],
            "error": "Invalid temperature value: not_a_temp"
        })

    @patch("subprocess.run")
    def test_check_nvidia_smi_available_success(self, mock_subprocess_run, gpu_monitor):
        """Test that nvidia-smi availability check succeeds."""
        mock_process = MagicMock()
        mock_process.stdout = "NVIDIA-SMI 525.105.17    Driver Version: 525.105.17    CUDA Version: 12.0"
        mock_subprocess_run.return_value = mock_process

        assert gpu_monitor.check_nvidia_smi_available() is True

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_check_nvidia_smi_not_available(self, mock_subprocess_run, gpu_monitor):
        """Test that nvidia-smi availability check fails if command not found."""
        assert gpu_monitor.check_nvidia_smi_available() is False
