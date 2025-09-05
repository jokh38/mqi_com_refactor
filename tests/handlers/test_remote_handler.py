import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import os
import stat

# Import the class we are testing
from src.handlers.remote_handler import RemoteHandler, ProcessingError
from src.config.settings import Settings
from src.utils.retry_policy import RetryPolicy

class TestRemoteHandler(unittest.TestCase):

    def setUp(self):
        """Set up a mock environment before each test."""
        # We manually start and stop the patcher to have access to the mock in setUp
        self.paramiko_patcher = patch('src.handlers.remote_handler.paramiko', autospec=True)
        self.os_walk_patcher = patch('src.handlers.remote_handler.os.walk', autospec=True)

        self.mock_paramiko = self.paramiko_patcher.start()
        self.mock_os_walk = self.os_walk_patcher.start()

        # Ensure the patchers are stopped after the test
        self.addCleanup(self.paramiko_patcher.stop)
        self.addCleanup(self.os_walk_patcher.stop)

        # Configure the mocks created by the patcher
        self.mock_ssh_client = self.mock_paramiko.SSHClient.return_value
        self.mock_sftp_client = self.mock_ssh_client.open_sftp.return_value

        # Mock dependencies for RemoteHandler
        self.mock_settings = MagicMock(spec=Settings)
        self.mock_logger = MagicMock()
        self.mock_retry_policy = MagicMock(spec=RetryPolicy)

        # Configure the retry policy to simply execute the function without retrying
        self.mock_retry_policy.execute.side_effect = lambda func, **kwargs: func()

        # Configure mock HPC connection settings
        self.mock_settings.get_hpc_connection.return_value = {
            "hostname": "test-hpc",
            "username": "testuser",
            "key_path": "/fake/key.pem",
            "timeout": 30
        }

        # Instantiate the handler for testing
        self.handler = RemoteHandler(
            settings=self.mock_settings,
            logger=self.mock_logger,
            retry_policy=self.mock_retry_policy
        )

    def test_connect_success(self):
        """Test successful connection to the HPC."""
        self.handler.connect()

        self.mock_paramiko.SSHClient.assert_called_once()
        self.mock_ssh_client.set_missing_host_key_policy.assert_called_with(self.mock_paramiko.AutoAddPolicy())
        self.mock_ssh_client.connect.assert_called_once_with(
            hostname="test-hpc",
            username="testuser",
            key_filename="/fake/key.pem",
            timeout=30
        )
        self.mock_ssh_client.open_sftp.assert_called_once()
        self.assertTrue(self.handler._connected)
        self.mock_logger.info.assert_any_call("HPC connection established successfully")

    def test_connect_failure_raises_processing_error(self):
        """Test that a connection failure raises a ProcessingError."""
        self.mock_ssh_client.connect.side_effect = Exception("Connection timed out")

        with self.assertRaises(ProcessingError) as cm:
            self.handler.connect()

        self.assertIn("Failed to connect to HPC system: Connection timed out", str(cm.exception))
        self.assertFalse(self.handler._connected)

    def test_disconnect_closes_clients(self):
        """Test that disconnect properly closes the SSH and SFTP clients."""
        self.handler.connect()
        self.handler.disconnect()

        self.mock_ssh_client.close.assert_called_once()
        self.mock_sftp_client.close.assert_called_once()
        self.assertFalse(self.handler._connected)

    def test_context_manager_connects_and_disconnects(self):
        """Test that the context manager correctly handles the connection lifecycle."""
        # The __enter__ and __exit__ methods will be called on a new instance
        with RemoteHandler(self.mock_settings, self.mock_logger, self.mock_retry_policy) as handler_instance:
            self.mock_ssh_client.connect.assert_called_once()
            self.assertTrue(handler_instance._connected)

        self.mock_ssh_client.close.assert_called_once()
        self.mock_sftp_client.close.assert_called_once()

    def test_upload_case_success(self):
        """Test successful upload of a case directory."""
        # Arrange
        self.mock_os_walk.return_value = [
            ('/local/case', ['subdir'], ['file1.txt']),
            ('/local/case/subdir', [], ['file2.txt']),
        ]

        # Patch the helper method on the instance to check calls
        with patch.object(self.handler, '_mkdir_p') as mock_mkdir_p:
            # Act
            success = self.handler.upload_case("case1", Path("/local/case"), "/remote/case")

            # Assert
            self.assertTrue(success)

            # Check that remote directories were created
            expected_mkdir_calls = [
                call(self.mock_sftp_client, '/remote/case'),
                call(self.mock_sftp_client, '/remote/case/subdir')
            ]
            mock_mkdir_p.assert_has_calls(expected_mkdir_calls, any_order=True)

            # Check that files were put
            expected_put_calls = [
                call(str(Path('/local/case/file1.txt')), '/remote/case/file1.txt'),
                call(str(Path('/local/case/subdir/file2.txt')), '/remote/case/subdir/file2.txt')
            ]
            self.mock_sftp_client.put.assert_has_calls(expected_put_calls, any_order=True)
            self.assertEqual(self.mock_sftp_client.put.call_count, 2)


    def test_execute_remote_command_success(self):
        """Test successful execution of a remote command."""
        # Arrange
        mock_channel = MagicMock()
        mock_channel.recv_exit_status.return_value = 0
        mock_stdout = MagicMock()
        mock_stdout.read.return_value = b'Success output'
        mock_stdout.channel = mock_channel
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b''

        self.mock_ssh_client.exec_command.return_value = (None, mock_stdout, mock_stderr)

        # Act
        result = self.handler.execute_remote_command("case1", "ls -l")

        # Assert
        self.assertTrue(result.success)
        self.assertEqual(result.output, 'Success output')
        self.assertEqual(result.error, '')
        self.assertEqual(result.return_code, 0)

    def test_upload_case_sftp_failure(self):
        """Test that upload_case returns False if sftp put fails."""
        # Arrange
        self.mock_os_walk.return_value = [('/local/case', [], ['file1.txt'])]
        self.mock_sftp_client.put.side_effect = Exception("Permission denied")

        # Act
        success = self.handler.upload_case("case1", Path("/local/case"), "/remote/case")

        # Assert
        self.assertFalse(success)
        self.mock_logger.error.assert_called_with("Case upload failed after retries", {
            "case_id": "case1",
            "error": "Permission denied"
        })

    @patch('src.handlers.remote_handler.Path', autospec=True)
    def test_download_results_success(self, mock_path_class):
        """Test successful download of a results directory."""
        # Arrange
        mock_local_path_instance = mock_path_class.return_value

        # Create two separate mock attribute objects
        mock_dir_item = MagicMock()
        mock_dir_item.filename = 'subdir'
        mock_dir_item.st_mode = stat.S_IFDIR

        mock_file_item = MagicMock()
        mock_file_item.filename = 'result.txt'
        mock_file_item.st_mode = stat.S_IFREG

        self.mock_sftp_client.listdir_attr.side_effect = [
            [mock_dir_item, mock_file_item], # For the top-level dir
            []  # For the recursive call on the empty subdir
        ]

        # Act
        success = self.handler.download_results("case1", "/remote/results", mock_local_path_instance)

        # Assert
        self.assertTrue(success)
        # Check that the local directory was created
        mock_local_path_instance.mkdir.assert_called_with(parents=True, exist_ok=True)

        # Check that listdir was called for both remote directories
        self.mock_sftp_client.listdir_attr.assert_has_calls([
            call('/remote/results'),
            call('/remote/results/subdir')
        ], any_order=True)

        # Check that the file was downloaded to the correct local path
        self.mock_sftp_client.get.assert_called_once()
        args, _ = self.mock_sftp_client.get.call_args
        self.assertEqual(args[0], '/remote/results/result.txt')
        # The second arg is a mock Path object, so we check how it was created
        self.assertEqual(str(args[1]), str(mock_local_path_instance / 'result.txt'))


    def test_submit_simulation_job_success(self):
        """Test successful submission of a simulation job."""
        # Arrange
        mock_sftp_file = MagicMock()
        self.mock_sftp_client.open.return_value.__enter__.return_value = mock_sftp_file

        # Mock the result of the sbatch command
        mock_exec_result = MagicMock()
        mock_exec_result.success = True
        mock_exec_result.output = "Submitted batch job 12345"
        mock_exec_result.error = ""
        with patch.object(self.handler, 'execute_remote_command', return_value=mock_exec_result) as mock_execute:
            # Act
            result = self.handler.submit_simulation_job("case1", "/remote/case", "GPU-UUID-1")

            # Assert
            self.assertTrue(result.success)
            self.assertEqual(result.job_id, "12345")

            # Check that the job script was written correctly
            self.mock_sftp_client.open.assert_called_with("/remote/case/submit_job.sh", 'w')
            # mock_sftp_file.write.assert_called_once() # Check content of script

            # Check that sbatch was called
            mock_execute.assert_called_with("case1", "sbatch /remote/case/submit_job.sh")

    def test_wait_for_job_completion_success(self):
        """Test waiting for a job that completes successfully."""
        # Arrange
        # Simulate squeue showing the job as running, then not finding it.
        running_result = MagicMock(success=True, output='RUNNING')
        # After it's not in squeue, sacct shows it completed.
        completed_result = MagicMock(success=True, output='COMPLETED')

        with patch.object(self.handler, 'execute_remote_command') as mock_execute:
            mock_execute.side_effect = [
                running_result,  # First poll to squeue
                MagicMock(success=True, output=''), # Second poll, job not in queue
                completed_result # Poll to sacct
            ]

            # Act
            status = self.handler.wait_for_job_completion("12345", timeout_seconds=60)

            # Assert
            self.assertTrue(status.completed)
            self.assertFalse(status.failed)
            # Check that the correct commands were run
            expected_calls = [
                call('job_polling', 'squeue -j 12345 --noheader --format=\'%T\''),
                call('job_polling', 'squeue -j 12345 --noheader --format=\'%T\''),
                call('job_history', "sacct -j 12345 --noheader --format='State' | head -1")
            ]
            mock_execute.assert_has_calls(expected_calls)

    def test_cleanup_remote_directory_success(self):
        """Test that cleanup executes the correct rm command."""
        # Arrange
        mock_exec_result = MagicMock(success=True)
        with patch.object(self.handler, 'execute_remote_command', return_value=mock_exec_result) as mock_execute:
            # Act
            success = self.handler.cleanup_remote_directory("/remote/case/to_delete")

            # Assert
            self.assertTrue(success)
            mock_execute.assert_called_once_with("cleanup", "rm -rf /remote/case/to_delete")


    def test_check_job_status_implemented(self):
        """Test that check_job_status correctly queries and parses job status."""
        # Arrange
        # Mock the squeue command to return a specific status
        mock_exec_result = MagicMock()
        mock_exec_result.success = True
        mock_exec_result.output = "RUNNING"

        with patch.object(self.handler, 'execute_remote_command', return_value=mock_exec_result) as mock_execute:
            # Act
            status_dict = self.handler.check_job_status("case1", "12345")

            # Assert
            # Check that the correct command was executed
            mock_execute.assert_called_once_with(
                "job_status_check", "squeue -j 12345 --noheader -o %T"
            )
            # Check that the returned dictionary is correct
            self.assertEqual(status_dict['job_id'], "12345")
            self.assertEqual(status_dict['status'], "RUNNING")
            self.assertIsNone(status_dict['error_message'])


if __name__ == '__main__':
    unittest.main()
