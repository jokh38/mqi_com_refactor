import pytest
from pathlib import Path
import os
import shutil
from unittest.mock import MagicMock

from src.utils.path_manager import PathManager
from src.domain.errors import ValidationError


@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    return MagicMock()


@pytest.fixture
def path_manager(mock_logger):
    """Fixture for a PathManager instance with a mock logger."""
    return PathManager(logger=mock_logger)


class TestPathManager:
    def test_validate_case_path_success(self, path_manager, tmp_path):
        """Test that a valid directory path is returned."""
        case_dir = tmp_path / "case1"
        case_dir.mkdir()
        validated_path = path_manager.validate_case_path(case_dir)
        assert validated_path == case_dir

    def test_validate_case_path_not_exists(self, path_manager, tmp_path):
        """Test that a non-existent path raises ValidationError."""
        with pytest.raises(ValidationError):
            path_manager.validate_case_path(tmp_path / "non_existent")

    def test_validate_case_path_is_file(self, path_manager, tmp_path):
        """Test that a file path raises ValidationError."""
        file_path = tmp_path / "file.txt"
        file_path.touch()
        with pytest.raises(ValidationError):
            path_manager.validate_case_path(file_path)

    def test_ensure_directory_exists(self, path_manager, tmp_path):
        """Test that a directory is created if it doesn't exist."""
        new_dir = tmp_path / "new_dir"
        path_manager.ensure_directory_exists(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()

    def test_ensure_directory_exists_already_exists(self, path_manager, tmp_path):
        """Test that it doesn't fail if the directory already exists."""
        existing_dir = tmp_path / "existing_dir"
        existing_dir.mkdir()
        path_manager.ensure_directory_exists(existing_dir)
        assert existing_dir.exists()

    def test_get_temp_directory(self, path_manager):
        """Test that a temporary directory is created."""
        temp_dir = path_manager.get_temp_directory()
        assert temp_dir.exists()
        assert temp_dir.is_dir()
        assert temp_dir.name.startswith("mqi_temp")
        shutil.rmtree(temp_dir)

    def test_cleanup_temp_directory(self, path_manager, tmp_path):
        """Test that a temporary directory is cleaned up."""
        temp_dir = tmp_path / "temp_to_clean"
        temp_dir.mkdir()
        (temp_dir / "file.txt").touch()
        path_manager.cleanup_temp_directory(temp_dir)
        assert not temp_dir.exists()

    def test_find_files_by_pattern(self, path_manager, tmp_path):
        """Test finding files by a glob pattern."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.log").touch()
        (tmp_path / "file3.txt").touch()
        found_files = path_manager.find_files_by_pattern(tmp_path, "*.txt")
        assert len(found_files) == 2
        assert tmp_path / "file1.txt" in found_files
        assert tmp_path / "file3.txt" in found_files

    def test_get_file_size(self, path_manager, tmp_path):
        """Test getting the size of a file."""
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("hello")
        assert path_manager.get_file_size(file_path) == 5

    def test_get_file_size_not_found(self, path_manager, tmp_path):
        """Test getting size of a non-existent file raises an error."""
        with pytest.raises(ValidationError):
            path_manager.get_file_size(tmp_path / "non_existent.txt")

    def test_is_directory_writable(self, path_manager, tmp_path):
        """Test checking if a directory is writable."""
        assert path_manager.is_directory_writable(tmp_path)

    @pytest.mark.skip(reason="Need to figure out how to test non-writable directories in CI")
    def test_is_directory_not_writable(self, path_manager, tmp_path):
        """Test checking if a directory is not writable."""
        # This test is tricky to set up reliably across platforms, especially in containers.
        # It often requires root permissions to change directory permissions to non-writable for the current user.
        # os.chmod(tmp_path, 0o444) # Read-only
        # assert not path_manager.is_directory_writable(tmp_path)
        # os.chmod(tmp_path, 0o755) # Restore permissions
        pass

    def test_get_relative_path(self, path_manager):
        """Test getting a relative path."""
        base_path = "/a/b/c"
        path = "/a/b/c/d/e.txt"
        relative_path = path_manager.get_relative_path(path, base_path)
        assert relative_path == Path("d/e.txt")

    def test_safe_copy_file(self, path_manager, tmp_path):
        """Test safely copying a file."""
        source = tmp_path / "source.txt"
        source.write_text("content")
        destination = tmp_path / "dest.txt"
        path_manager.safe_copy_file(source, destination)
        assert destination.exists()
        assert destination.read_text() == "content"

    def test_safe_copy_file_source_not_found(self, path_manager, tmp_path):
        """Test copying a non-existent file raises an error."""
        with pytest.raises(ValidationError):
            path_manager.safe_copy_file(tmp_path / "non_existent", tmp_path / "dest.txt")

    def test_safe_move_file(self, path_manager, tmp_path):
        """Test safely moving a file."""
        source = tmp_path / "source.txt"
        source.write_text("move content")
        destination = tmp_path / "dest.txt"
        path_manager.safe_move_file(source, destination)
        assert not source.exists()
        assert destination.exists()
        assert destination.read_text() == "move content"

    def test_get_case_metadata(self, path_manager, tmp_path):
        """Test getting metadata from a case directory."""
        case_dir = tmp_path / "case_meta"
        case_dir.mkdir()
        (case_dir / "file1.txt").write_text("12345")
        (case_dir / "subdir").mkdir()
        (case_dir / "subdir" / "file2.txt").write_text("1234567890")
        metadata = path_manager.get_case_metadata(case_dir)
        assert metadata["file_count"] == 2
        assert metadata["total_size_bytes"] == 15

    def test_logging_is_called(self, path_manager, mock_logger, tmp_path):
        """Test that logging is called for operations."""
        new_dir = tmp_path / "logged_dir"
        path_manager.ensure_directory_exists(new_dir)
        mock_logger.debug.assert_called_with(
            "Path operation",
            {"operation": "ensure_directory", "path": str(new_dir), "success": True}
        )
