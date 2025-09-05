import pytest
from unittest.mock import MagicMock, patch, ANY
import subprocess
from concurrent.futures import Future

from src.infrastructure.process_manager import ProcessManager, CommandExecutor
from src.config.settings import ProcessingConfig
from src.domain.errors import ProcessingError

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def processing_config():
    return ProcessingConfig(max_workers=4)

@pytest.fixture
def command_executor(mock_logger):
    return CommandExecutor(logger=mock_logger, default_timeout=10)

class TestProcessManager:
    @patch("src.infrastructure.process_manager.ProcessPoolExecutor")
    def test_start_and_shutdown(self, mock_executor_cls, processing_config, mock_logger):
        """Test that the process manager starts and shuts down the executor."""
        manager = ProcessManager(config=processing_config, logger=mock_logger)
        manager.start()
        assert mock_executor_cls.called

        mock_executor_instance = mock_executor_cls.return_value
        manager.shutdown()
        mock_executor_instance.shutdown.assert_called_once_with(wait=True)

    @patch("src.infrastructure.process_manager.ProcessPoolExecutor")
    def test_submit_case_processing(self, mock_executor_cls, processing_config, mock_logger):
        """Test submitting a case to the process pool."""
        manager = ProcessManager(config=processing_config, logger=mock_logger)
        manager.start()

        mock_executor = mock_executor_cls.return_value
        mock_future = Future()
        mock_executor.submit.return_value = mock_future

        worker_func = MagicMock()
        case_id = "case123"
        case_path = "/path/to/case"

        process_id = manager.submit_case_processing(worker_func, case_id, case_path)

        assert process_id.startswith(f"case_{case_id}")
        mock_executor.submit.assert_called_once_with(worker_func, case_id, case_path)
        assert manager.is_process_active(process_id)

    @patch("src.infrastructure.process_manager.ProcessPoolExecutor")
    def test_process_completion_callback(self, mock_executor_cls, processing_config, mock_logger):
        """Test the callback function for process completion."""
        manager = ProcessManager(config=processing_config, logger=mock_logger)
        manager.start()

        # Simulate submitting a process
        mock_executor = mock_executor_cls.return_value
        future = Future()
        mock_executor.submit.return_value = future
        process_id = manager.submit_case_processing(MagicMock(), "case123", "/path")

        # Simulate successful completion
        future.set_result("Success")
        manager._process_completed(process_id, future)

        mock_logger.info.assert_called_with("Process completed successfully", ANY)
        assert not manager.is_process_active(process_id)


class TestCommandExecutor:
    @patch("subprocess.run")
    def test_execute_command_success(self, mock_run, command_executor):
        """Test successful command execution."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="output")
        result = command_executor.execute_command(["ls", "-l"])

        assert result.returncode == 0
        assert result.stdout == "output"
        mock_run.assert_called_once()

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=10))
    def test_execute_command_timeout(self, mock_run, command_executor):
        """Test command timeout raises ProcessingError."""
        with pytest.raises(ProcessingError, match="timed out"):
            command_executor.execute_command(["sleep", "20"])

    @patch("subprocess.run", side_effect=subprocess.CalledProcessError(returncode=1, cmd="test"))
    def test_execute_command_error(self, mock_run, command_executor):
        """Test command failure raises ProcessingError."""
        with pytest.raises(ProcessingError, match="failed"):
            command_executor.execute_command(["invalid-command"])

    @patch("subprocess.Popen")
    def test_execute_command_async(self, mock_popen, command_executor):
        """Test asynchronous command execution."""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        process = command_executor.execute_command_async(["./long_script.sh"])

        assert process is mock_process
        mock_popen.assert_called_once_with(
            ["./long_script.sh"],
            cwd=None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=None
        )
