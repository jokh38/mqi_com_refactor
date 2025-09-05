# Tests for src/config/constants.py and src/config/settings.py
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from src.config import constants
from src.config.settings import Settings


# ===== Tests for constants.py =====


def test_database_schema_constants():
    """Tests the database schema constants."""
    assert constants.DB_SCHEMA_VERSION == "1.0"
    assert constants.CASES_TABLE_NAME == "cases"
    assert constants.GPU_RESOURCES_TABLE_NAME == "gpu_resources"
    assert constants.WORKFLOW_HISTORY_TABLE_NAME == "workflow_history"


def test_file_system_constants():
    """Tests the file system constants."""
    assert constants.DICOM_FILE_EXTENSIONS == [".dcm", ".dicom"]
    assert constants.TPS_INPUT_FILE_NAME == "moqui_tps.in"
    assert constants.TPS_OUTPUT_FILE_PATTERN == "dose_*.raw"
    assert constants.LOG_FILE_EXTENSIONS == [".log", ".out", ".err"]
    assert constants.REQUIRED_CASE_FILES == [
        "input.dat", "geometry.dcm", "structure.dcm"
    ]


def test_command_templates_constants():
    """Tests the command templates."""
    assert constants.NVIDIA_SMI_QUERY_COMMAND == (
        "nvidia-smi --query-gpu=index,uuid,utilization.gpu,memory.used,"
        "memory.total,temperature.gpu --format=csv,noheader,nounits"
    )
    assert constants.PUEUE_STATUS_COMMAND == "pueue status --json"
    assert constants.PUEUE_ADD_COMMAND_TEMPLATE == (
        "pueue add --group gpu{gpu_id} '{command}'"
    )


def test_workflow_state_names_constants():
    """Tests the workflow state names."""
    expected_steps = [
        "PENDING", "PREPROCESSING", "TPS_GENERATION", "HPC_SUBMISSION",
        "SIMULATION_RUNNING", "POSTPROCESSING", "COMPLETED", "FAILED"
    ]
    assert constants.WORKFLOW_STEPS == expected_steps


def test_validation_constants():
    """Tests the validation constants."""
    assert constants.MAX_CASE_ID_LENGTH == 64
    assert constants.MIN_GPU_MEMORY_MB == 2048
    assert constants.MAX_BEAM_NUMBERS == 100
    assert constants.CASE_ID_VALID_CHARS == (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    )


def test_error_message_templates_constants():
    """Tests the error message templates."""
    assert constants.ERROR_MSG_CASE_NOT_FOUND == (
        "Case '{case_id}' not found in database"
    )
    assert constants.ERROR_MSG_GPU_NOT_AVAILABLE == (
        "No available GPU found for case '{case_id}'"
    )
    assert constants.ERROR_MSG_INVALID_CASE_PATH == (
        "Invalid case path: '{path}' does not exist or is not accessible"
    )
    assert constants.ERROR_MSG_TPS_GENERATION_FAILED == (
        "TPS generation failed for case '{case_id}': {details}"
    )


def test_ui_display_constants():
    """Tests the UI display constants."""
    assert constants.TERMINAL_MIN_WIDTH == 120
    assert constants.TERMINAL_MIN_HEIGHT == 30
    assert constants.TABLE_MAX_ROWS == 50
    assert constants.PROGRESS_BAR_WIDTH == 20
    expected_colors = {
        "PENDING": "yellow", "RUNNING": "blue", "COMPLETED": "green",
        "FAILED": "red", "CANCELLED": "orange"
    }
    assert constants.STATUS_COLORS == expected_colors


def test_system_resource_limits_constants():
    """Tests the system resource limits."""
    assert constants.MAX_CONCURRENT_CASES == 10
    assert constants.MAX_LOG_LINES_PER_CASE == 10000
    assert constants.MAX_ERROR_HISTORY_ENTRIES == 1000


def test_moqui_tps_parameter_names_constants():
    """Tests the MOQUI TPS parameter names."""
    assert constants.TPS_REQUIRED_PARAMS == [
        'GPUID', 'DicomDir', 'logFilePath', 'OutputDir', 'BeamNumbers'
    ]
    expected_fixed_params = {
        'RandomSeed': -1932780356,
        'UseAbsolutePath': True,
        'Verbosity': 0,
        'UsingPhantomGeo': True,
        'Scorer': 'Dose',
        'SourceType': 'FluenceMap',
        'SimulationType': 'perBeam',
        'ScoreToCTGrid': True,
        'OutputFormat': 'raw',
        'OverwriteResults': True,
        'ParticlesPerHistory': 1,
        'TwoCentimeterMode': True
    }
    assert constants.TPS_FIXED_PARAMS == expected_fixed_params


# ===== Tests for settings.py =====


@pytest.fixture
def mock_env_vars():
    """Fixture to set up mock environment variables."""
    env_vars = {
        "MQI_DB_PATH": "/tmp/test.db",
        "MQI_DB_TIMEOUT": "60",
        "MQI_MAX_WORKERS": "8",
        "MQI_LOG_LEVEL": "DEBUG",
        "MQI_STRUCTURED_LOGGING": "false"
    }
    with patch.dict(os.environ, env_vars):
        yield


def test_settings_load_from_env(mock_env_vars):
    """Tests that settings are correctly loaded from environment variables."""
    settings = Settings()

    # Test database config
    assert settings.database.db_path == Path("/tmp/test.db")
    assert settings.database.timeout == 60
    assert settings.database.journal_mode == "WAL"  # Default

    # Test processing config
    assert settings.processing.max_workers == 8
    assert settings.processing.case_timeout == 3600  # Default

    # Test logging config
    assert settings.logging.log_level == "DEBUG"
    assert not settings.logging.structured_logging


def test_settings_defaults_without_env():
    """Tests that default settings are used when no env vars are set."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()

        # Test database config
        assert settings.database.db_path == Path("database/mqi.db")
        assert settings.database.timeout == 30

        # Test processing config
        assert settings.processing.max_workers == 4

        # Test logging config
        assert settings.logging.log_level == "INFO"
        assert settings.logging.structured_logging


@pytest.fixture
def test_config_file(tmp_path):
    """Fixture to create a temporary config file for testing."""
    config_content = {
        "database": {
            "journal_mode": "DELETE",
            "cache_size_mb": 4,
            "busy_timeout_ms": 10000,
            "synchronous_mode": "FULL"
        },
        "application": {
            "max_workers": 16,
            "scan_interval_seconds": 30
        },
        "paths": {
            "base_directory": "/mnt/data",
            "local": {
                "scan_directory": "{base_directory}/input",
                "database_path": "{base_directory}/db/prod.db"
            },
            "hpc": {
                "remote_base_dir": "/lustre/user/mqi"
            }
        },
        "executables": {
            "python_interpreter": "{base_directory}/venv/bin/python"
        },
        "hpc_connection": {
            "host": "hpc.cluster",
            "user": "testuser"
        },
        "moqui_tps_parameters": {
            "SomeSetting": "SomeValue"
        }
    }
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(config_content, f)
    return config_path


def test_settings_load_from_file(test_config_file):
    """Tests that settings are correctly loaded from a YAML file."""
    settings = Settings(config_path=test_config_file)

    # Test that YAML values override defaults
    assert settings.processing.max_workers == 16
    assert settings.database.journal_mode == "DELETE"

    # Test get_case_directories
    dirs = settings.get_case_directories()
    assert dirs["scan"] == Path("/mnt/data/input")

    # Test get_database_path
    db_path = settings.get_database_path()
    assert db_path == Path("/mnt/data/db/prod.db")

    # Test get_executables
    execs = settings.get_executables()
    assert execs["python_interpreter"] == "/mnt/data/venv/bin/python"

    # Test get_hpc_connection
    hpc_conn = settings.get_hpc_connection()
    assert hpc_conn["host"] == "hpc.cluster"

    # Test get_hpc_paths
    hpc_paths = settings.get_hpc_paths()
    assert hpc_paths["remote_base_dir"] == "/lustre/user/mqi"

    # Test get_moqui_tps_parameters
    moqui_params = settings.get_moqui_tps_parameters()
    assert moqui_params["SomeSetting"] == "SomeValue"


def test_settings_yaml_overrides_env(mock_env_vars, test_config_file):
    """Tests that YAML file settings override environment variables."""
    settings = Settings(config_path=test_config_file)

    # max_workers is 8 in env, 16 in yaml
    assert settings.processing.max_workers == 16
    # journal_mode is WAL in env, DELETE in yaml
    assert settings.database.journal_mode == "DELETE"


def test_settings_non_existent_file(capsys):
    """Tests that the system handles a non-existent config file gracefully."""
    settings = Settings(config_path=Path("non_existent_file.yaml"))

    # Assert that we fall back to defaults/env vars
    assert settings.processing.max_workers == 4  # default

    # Assert that no warning is printed for a non-existent file
    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.fixture
def invalid_config_file(tmp_path):
    """Fixture to create a temporary invalid config file for testing."""
    config_path = tmp_path / "invalid_config.yaml"
    with open(config_path, 'w') as f:
        f.write("database: { journal_mode: [DELETE")  # Malformed YAML
    return config_path


def test_settings_invalid_file(invalid_config_file, capsys):
    """Tests that a warning is printed for a malformed config file."""
    settings = Settings(config_path=invalid_config_file)

    # Assert that we fall back to defaults
    assert settings.processing.max_workers == 4  # default

    # Assert that a warning is printed
    captured = capsys.readouterr()
    assert "Warning: Could not load config file" in captured.out
