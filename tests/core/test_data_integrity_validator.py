# =====================================================================================
# Target File: tests/core/test_data_integrity_validator.py
# =====================================================================================
"""Tests for the data integrity validator module."""

import unittest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import tempfile
import os

from src.core.data_integrity_validator import DataIntegrityValidator
from src.infrastructure.logging_handler import StructuredLogger
from src.domain.errors import ProcessingError


class TestDataIntegrityValidator(unittest.TestCase):
    """Test cases for DataIntegrityValidator."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = Mock(spec=StructuredLogger)
        self.validator = DataIntegrityValidator(self.mock_logger)

    def test_init(self):
        """Test validator initialization."""
        self.assertEqual(self.validator.logger, self.mock_logger)

    @patch('src.core.data_integrity_validator.pydicom.dcmread')
    def test_find_rtplan_file_success(self, mock_dcmread):
        """Test successful RT plan file discovery."""
        # Setup mock DICOM dataset
        mock_ds = Mock()
        mock_ds.get.return_value = "RTPLAN"
        mock_dcmread.return_value = mock_ds

        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)

            # Create a mock RT plan file
            rtplan_file = case_path / "rtplan.dcm"
            rtplan_file.touch()

            result = self.validator.find_rtplan_file(case_path)

            self.assertEqual(result, rtplan_file)
            mock_dcmread.assert_called_once()

    def test_find_rtplan_file_not_found(self):
        """Test RT plan file not found."""
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)

            result = self.validator.find_rtplan_file(case_path)

            self.assertIsNone(result)

    def test_count_beam_subdirectories(self):
        """Test beam subdirectory counting."""
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)

            # Create some subdirectories
            (case_path / "beam1").mkdir()
            (case_path / "beam2").mkdir()
            (case_path / "beam3").mkdir()

            # Create a file (should not be counted)
            (case_path / "file.txt").touch()

            result = self.validator.count_beam_subdirectories(case_path)

            self.assertEqual(result, 3)

    @patch('src.core.data_integrity_validator.pydicom.dcmread')
    def test_parse_rtplan_beam_count_ion_beams(self, mock_dcmread):
        """Test RT plan parsing with ion beam sequence."""
        # Setup mock DICOM dataset with ion beams
        mock_ds = Mock()
        mock_ds.get.return_value = "RTPLAN"

        # Create mock ion beam sequence
        mock_beam1 = Mock()
        mock_beam1.BeamDescription = "Treatment"
        mock_beam1.BeamName = "Beam1"

        mock_beam2 = Mock()
        mock_beam2.BeamDescription = "Treatment"
        mock_beam2.BeamName = "Beam2"

        mock_setup_beam = Mock()
        mock_setup_beam.BeamDescription = "Site Setup"
        mock_setup_beam.BeamName = "SETUP"

        mock_ds.IonBeamSequence = [mock_beam1, mock_beam2, mock_setup_beam]
        mock_dcmread.return_value = mock_ds

        with tempfile.TemporaryDirectory() as temp_dir:
            rtplan_path = Path(temp_dir) / "rtplan.dcm"
            rtplan_path.touch()

            result = self.validator.parse_rtplan_beam_count(rtplan_path)

            self.assertEqual(result, 2)  # Should exclude setup beam

    @patch('src.core.data_integrity_validator.pydicom.dcmread')
    def test_parse_rtplan_beam_count_invalid_modality(self, mock_dcmread):
        """Test RT plan parsing with invalid modality."""
        mock_ds = Mock()
        mock_ds.get.return_value = "CT"  # Not RTPLAN
        mock_dcmread.return_value = mock_ds

        with tempfile.TemporaryDirectory() as temp_dir:
            rtplan_path = Path(temp_dir) / "rtplan.dcm"
            rtplan_path.touch()

            with self.assertRaises(ProcessingError) as context:
                self.validator.parse_rtplan_beam_count(rtplan_path)

            self.assertIn("not an RT plan", str(context.exception))

    def test_validate_data_transfer_completion_success(self):
        """Test successful data transfer validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)
            case_id = "test_case"

            # Create subdirectories
            (case_path / "beam1").mkdir()
            (case_path / "beam2").mkdir()

            # Mock the validator methods
            with patch.object(self.validator, 'find_rtplan_file') as mock_find, \
                 patch.object(self.validator, 'parse_rtplan_beam_count') as mock_parse:

                mock_find.return_value = case_path / "rtplan.dcm"
                mock_parse.return_value = 2  # Expect 2 beams

                is_valid, error_msg = self.validator.validate_data_transfer_completion(case_id, case_path)

                self.assertTrue(is_valid)
                self.assertEqual(error_msg, "")

    def test_validate_data_transfer_completion_incomplete(self):
        """Test data transfer validation with incomplete transfer."""
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)
            case_id = "test_case"

            # Create only 1 subdirectory
            (case_path / "beam1").mkdir()

            # Mock the validator methods
            with patch.object(self.validator, 'find_rtplan_file') as mock_find, \
                 patch.object(self.validator, 'parse_rtplan_beam_count') as mock_parse:

                mock_find.return_value = case_path / "rtplan.dcm"
                mock_parse.return_value = 3  # Expect 3 beams but only have 1

                is_valid, error_msg = self.validator.validate_data_transfer_completion(case_id, case_path)

                self.assertFalse(is_valid)
                self.assertIn("Data transfer incomplete", error_msg)
                self.assertIn("Expected 3 beams", error_msg)
                self.assertIn("found 1 subdirectories", error_msg)

    def test_validate_data_transfer_completion_no_rtplan(self):
        """Test data transfer validation with no RT plan file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)
            case_id = "test_case"

            # Mock find_rtplan_file to return None
            with patch.object(self.validator, 'find_rtplan_file') as mock_find:
                mock_find.return_value = None

                is_valid, error_msg = self.validator.validate_data_transfer_completion(case_id, case_path)

                self.assertFalse(is_valid)
                self.assertIn("No RT plan file found", error_msg)

    @patch('src.core.data_integrity_validator.pydicom.dcmread')
    def test_get_beam_information(self, mock_dcmread):
        """Test beam information extraction."""
        # Setup mock DICOM dataset
        mock_ds = Mock()
        mock_ds.get.side_effect = lambda key, default=None: {
            "PatientID": "12345",
            "RTPlanLabel": "Test Plan",
            "RTPlanDate": "20231201"
        }.get(key, default)

        # Create mock ion beam sequence
        mock_beam = Mock()
        mock_beam.BeamDescription = "Treatment"
        mock_beam.BeamName = "Beam1"
        mock_beam.TreatmentMachineName = "TrueBeam"

        mock_ds.IonBeamSequence = [mock_beam]
        mock_dcmread.return_value = mock_ds

        with tempfile.TemporaryDirectory() as temp_dir:
            case_path = Path(temp_dir)
            rtplan_file = case_path / "rtplan.dcm"
            rtplan_file.touch()

            # Mock find_rtplan_file
            with patch.object(self.validator, 'find_rtplan_file') as mock_find:
                mock_find.return_value = rtplan_file

                result = self.validator.get_beam_information(case_path)

                self.assertEqual(result["beam_count"], 1)
                self.assertEqual(result["patient_id"], "12345")
                self.assertEqual(result["plan_label"], "Test Plan")
                self.assertEqual(len(result["beams"]), 1)
                self.assertEqual(result["beams"][0]["beam_name"], "Beam1")


if __name__ == '__main__':
    unittest.main()