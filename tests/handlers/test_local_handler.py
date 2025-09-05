import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

import subprocess
from src.handlers.local_handler import LocalHandler
from src.config.settings import Settings, ProcessingConfig
from src.domain.errors import ProcessingError

class TestLocalHandler(unittest.TestCase):

    def setUp(self):
        """Set up a mock environment for each test."""
        self.mock_settings = MagicMock(spec=Settings)

        # Create a mock for the 'processing' attribute and assign it.
        mock_processing_config = MagicMock(spec=ProcessingConfig)
        mock_processing_config.case_timeout = 300
        self.mock_settings.processing = mock_processing_config

        self.mock_logger = MagicMock()
        self.mock_command_executor = MagicMock()
        self.mock_retry_policy = MagicMock()

        # The retry policy mock will just execute the function it's given, simulating a single attempt.
        self.mock_retry_policy.execute.side_effect = lambda func, **kwargs: func()

        # Configure mock settings for executables
        self.mock_settings.get_executables.return_value = {
            "python_interpreter": "python3",
            "mqi_interpreter": "/path/to/mqi_interpreter.py",
            "raw_to_dicom": "/path/to/raw_to_dicom.py"
        }

        # Instantiate the handler with mocked dependencies
        self.handler = LocalHandler(
            settings=self.mock_settings,
            logger=self.mock_logger,
            command_executor=self.mock_command_executor,
            retry_policy=self.mock_retry_policy
        )

    def test_validate_case_structure_success(self):
        """Test validation succeeds for a valid case structure."""
        mock_case_path = MagicMock(spec=Path)
        mock_case_path.exists.return_value = True
        mock_case_path.is_dir.return_value = True

        # Mock the check for 'case_config.yaml'
        mock_required_file = MagicMock(spec=Path)
        mock_required_file.exists.return_value = True
        mock_case_path.__truediv__.return_value = mock_required_file

        result = self.handler.validate_case_structure(mock_case_path)

        self.assertTrue(result)
        self.mock_logger.debug.assert_called_once()
        self.mock_logger.error.assert_not_called()

    def test_validate_case_structure_path_does_not_exist(self):
        """Test validation fails if the case path does not exist."""
        mock_case_path = MagicMock(spec=Path)
        mock_case_path.exists.return_value = False

        result = self.handler.validate_case_structure(mock_case_path)

        self.assertFalse(result)
        self.mock_logger.error.assert_called_with("Case path does not exist", {"case_path": str(mock_case_path)})

    def test_validate_case_structure_path_is_not_a_directory(self):
        """Test validation fails if the case path is not a directory."""
        mock_case_path = MagicMock(spec=Path)
        mock_case_path.exists.return_value = True
        mock_case_path.is_dir.return_value = False

        result = self.handler.validate_case_structure(mock_case_path)

        self.assertFalse(result)
        self.mock_logger.error.assert_called_with("Case path is not a directory", {"case_path": str(mock_case_path)})

    def test_validate_case_structure_missing_required_file_succeeds_with_warning(self):
        """Test validation succeeds but logs a warning if 'case_config.yaml' is missing."""
        mock_case_path = MagicMock(spec=Path)
        mock_case_path.exists.return_value = True
        mock_case_path.is_dir.return_value = True

        mock_required_file = MagicMock(spec=Path)
        mock_required_file.exists.return_value = False
        mock_case_path.__truediv__.return_value = mock_required_file

        result = self.handler.validate_case_structure(mock_case_path)

        self.assertTrue(result) # Current implementation allows this
        self.mock_logger.warning.assert_called_with(f"Required file not found: {mock_required_file}")

    def test_execute_mqi_interpreter_success(self):
        """Test successful execution of the MQI interpreter."""
        # Arrange
        mock_case_path = Path("/fake/case")
        mock_result = subprocess.CompletedProcess(args=[], stdout="Success", stderr="", returncode=0)
        self.mock_command_executor.execute_command.return_value = mock_result

        # Act
        result = self.handler.execute_mqi_interpreter("case1", mock_case_path)

        # Assert
        self.assertTrue(result.success)
        self.assertEqual(result.output, "Success")
        self.assertEqual(result.return_code, 0)
        self.mock_command_executor.execute_command.assert_called_once()
        self.mock_logger.info.assert_called()
        self.mock_logger.error.assert_not_called()

    def test_execute_mqi_interpreter_failure(self):
        """Test failed execution of the MQI interpreter."""
        # Arrange
        mock_case_path = Path("/fake/case")
        error_instance = ProcessingError("Command failed")
        error_instance.return_code = 1  # Manually set the attribute
        self.mock_command_executor.execute_command.side_effect = error_instance

        # Act
        result = self.handler.execute_mqi_interpreter("case1", mock_case_path)

        # Assert
        self.assertFalse(result.success)
        self.assertIn("Command failed", result.error)
        self.assertEqual(result.return_code, 1)
        self.mock_logger.error.assert_called()

    def test_execute_mqi_interpreter_retries_on_failure(self):
        """Test that the retry policy is invoked on failure."""
        # Arrange
        mock_case_path = Path("/fake/case")
        error_instance = ProcessingError("Command failed")
        error_instance.return_code = 1  # Manually set the attribute
        self.mock_command_executor.execute_command.side_effect = error_instance

        # Act
        self.handler.execute_mqi_interpreter("case1", mock_case_path)

        # Assert
        self.mock_retry_policy.execute.assert_called_once()
        # Get the arguments passed to the mock
        args, kwargs = self.mock_retry_policy.execute.call_args
        self.assertEqual(kwargs['operation_name'], 'mqi_interpreter')


    def test_execute_raw_to_dicom_success(self):
        """Test successful execution of the RawToDicom converter."""
        # Arrange
        mock_case_path = Path("/fake/case")
        mock_result = subprocess.CompletedProcess(args=[], stdout="Success", stderr="", returncode=0)
        self.mock_command_executor.execute_command.return_value = mock_result

        # Act
        result = self.handler.execute_raw_to_dicom("case1", mock_case_path)

        # Assert
        self.assertTrue(result.success)
        self.mock_command_executor.execute_command.assert_called_once()
        self.mock_logger.error.assert_not_called()

    def test_execute_raw_to_dicom_failure(self):
        """Test failed execution of the RawToDicom converter."""
        # Arrange
        mock_case_path = Path("/fake/case")
        error_instance = ProcessingError("Command failed")
        error_instance.return_code = 1
        self.mock_command_executor.execute_command.side_effect = error_instance

        # Act
        result = self.handler.execute_raw_to_dicom("case1", mock_case_path)

        # Assert
        self.assertFalse(result.success)
        self.assertEqual(result.return_code, 1)
        self.mock_retry_policy.execute.assert_called_once()

    def test_run_mqi_interpreter_builds_correct_command(self):
        """Test that the wrapper method builds the command with correct arguments."""
        # Arrange
        mock_case_path = Path("/fake/case1")
        input_file = mock_case_path / "input.mqi"
        output_file = mock_case_path / "output.json"

        # We need to spy on the actual method to check the arguments it's called with
        with patch.object(self.handler, 'execute_mqi_interpreter', return_value=None) as mock_execute:
            # Act
            self.handler.run_mqi_interpreter(input_file, output_file, mock_case_path)

            # Assert
            mock_execute.assert_called_once_with(
                "case1",
                mock_case_path,
                {"input": str(input_file), "output": str(output_file)}
            )

    def test_run_raw_to_dcm_builds_correct_command(self):
        """Test that the wrapper method builds the command with correct arguments."""
        # Arrange
        mock_case_path = Path("/fake/case1")
        input_file = mock_case_path / "input.raw"
        output_dir = mock_case_path / "output_dcm"

        with patch.object(self.handler, 'execute_raw_to_dicom', return_value=None) as mock_execute:
            # Act
            self.handler.run_raw_to_dcm(input_file, output_dir, mock_case_path)

            # Assert
            mock_execute.assert_called_once_with(
                "case1",
                mock_case_path,
                {"input": str(input_file), "output": str(output_dir)}
            )


if __name__ == '__main__':
    unittest.main()
