import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import stat

from src.handlers.remote_handler import RemoteHandler, ProcessingError
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy

@pytest.fixture
def mock_paramiko(mocker):
    return mocker.patch('src.handlers.remote_handler.paramiko', autospec=True)

@pytest.fixture
def mock_retry_policy():
    retry_policy = MagicMock(spec=RetryPolicy)
    retry_policy.execute.side_effect = lambda func, **kwargs: func()
    return retry_policy

@pytest.fixture
def mock_logger():
    return MagicMock()

@pytest.fixture
def mock_settings(tmp_path):
    config_content = """
hpc_connection:
  host: "test-hpc"
  user: "testuser"
  ssh_key_path: "/fake/key.pem"
  connection_timeout_seconds: 30
"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(config_content)
    return Settings(config_file)

@pytest.fixture
def handler(mock_settings, mock_logger, mock_retry_policy):
    return RemoteHandler(
        settings=mock_settings,
        logger=mock_logger,
        retry_policy=mock_retry_policy
    )

class TestRemoteHandler:

    def test_connect_success(self, handler, mock_paramiko):
        mock_ssh_client = mock_paramiko.SSHClient.return_value
        handler.connect()
        mock_paramiko.SSHClient.assert_called_once()
        mock_ssh_client.set_missing_host_key_policy.assert_called_with(mock_paramiko.AutoAddPolicy())
        mock_ssh_client.connect.assert_called_once_with(
            hostname="test-hpc",
            username="testuser",
            key_filename="/fake/key.pem",
            timeout=30
        )
        mock_ssh_client.open_sftp.assert_called_once()
        assert handler._connected

    def test_connect_failure_raises_processing_error(self, handler, mock_paramiko):
        mock_paramiko.SSHClient.return_value.connect.side_effect = Exception("Connection timed out")
        with pytest.raises(ProcessingError, match="Failed to connect to HPC system: Connection timed out"):
            handler.connect()
        assert not handler._connected

    def test_execute_remote_command_success(self, handler, mock_paramiko):
        mock_ssh_client = mock_paramiko.SSHClient.return_value
        mock_channel = MagicMock()
        mock_channel.recv_exit_status.return_value = 0
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b'Success output'
        mock_stdout.channel = mock_channel
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b''
        mock_ssh_client.exec_command.return_value = (None, mock_stdout, mock_stderr)

        result = handler.execute_remote_command("context1", "ls -l")

        assert result.success
        assert result.output == 'Success output'
        assert result.return_code == 0

    def test_submit_simulation_job_success(self, handler, mock_paramiko):
        mock_ssh_client = mock_paramiko.SSHClient.return_value
        mock_sftp_client = mock_ssh_client.open_sftp.return_value
        mock_sftp_file = MagicMock()
        mock_sftp_client.open.return_value.__enter__.return_value = mock_sftp_file

        mock_exec_result = MagicMock()
        mock_exec_result.success = True
        mock_exec_result.output = "Submitted batch job 12345"

        with patch.object(handler, 'execute_remote_command', return_value=mock_exec_result) as mock_execute:
            result = handler.submit_simulation_job(
                beam_id="beam1",
                remote_beam_dir="/remote/case/beam1",
                gpu_uuid="GPU-UUID-1"
            )
            assert result.success
            assert result.job_id == "12345"
            mock_sftp_client.open.assert_called_with("/remote/case/beam1/submit_job.sh", 'w')
            mock_execute.assert_called_with("beam1", "sbatch /remote/case/beam1/submit_job.sh")

    def test_check_job_status_implemented(self, handler):
        mock_exec_result = MagicMock()
        mock_exec_result.success = True
        mock_exec_result.output = "RUNNING"

        with patch.object(handler, 'execute_remote_command', return_value=mock_exec_result) as mock_execute:
            status_dict = handler.check_job_status("12345")
            mock_execute.assert_called_once_with("job_status_check", "squeue -j 12345 --noheader -o %T")
            assert status_dict['job_id'] == "12345"
            assert status_dict['status'] == "RUNNING"
