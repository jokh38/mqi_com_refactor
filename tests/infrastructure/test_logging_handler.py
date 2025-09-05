import pytest
import json
import logging
from pathlib import Path

from src.infrastructure.logging_handler import StructuredLogger, LoggerFactory
from src.config.settings import LoggingConfig

@pytest.fixture
def log_dir(tmp_path):
    """Fixture for a temporary log directory."""
    return tmp_path / "logs"

@pytest.fixture
def structured_log_config(log_dir):
    """Fixture for a structured logging configuration."""
    return LoggingConfig(
        log_dir=log_dir,
        log_level="DEBUG",
        structured_logging=True,
        max_file_size=1,
        backup_count=1
    )

@pytest.fixture
def unstructured_log_config(log_dir):
    """Fixture for an unstructured logging configuration."""
    return LoggingConfig(
        log_dir=log_dir,
        log_level="INFO",
        structured_logging=False,
        max_file_size=1,
        backup_count=1
    )

class TestStructuredLogger:
    def test_structured_logging(self, structured_log_config, log_dir):
        """Test that logs are written in JSON format when structured_logging is True."""
        logger_name = "test_structured"
        logger = StructuredLogger(logger_name, structured_log_config)

        logger.info("This is a test", context={"key": "value"})

        log_file = log_dir / f"{logger_name}.log"
        assert log_file.exists()

        log_content = log_file.read_text()
        log_data = json.loads(log_content)

        assert log_data["level"] == "INFO"
        assert log_data["message"] == "This is a test"
        assert log_data["context"]["key"] == "value"

    def test_unstructured_logging(self, unstructured_log_config, log_dir):
        """Test that logs are written in plain text when structured_logging is False."""
        logger_name = "test_unstructured"
        logger = StructuredLogger(logger_name, unstructured_log_config)

        logger.info("This is a plain text message")

        log_file = log_dir / f"{logger_name}.log"
        assert log_file.exists()

        log_content = log_file.read_text()
        assert "INFO" in log_content
        assert "This is a plain text message" in log_content
        with pytest.raises(json.JSONDecodeError):
            json.loads(log_content)

    def test_log_level(self, unstructured_log_config, log_dir):
        """Test that messages below the configured log level are ignored."""
        logger_name = "test_log_level"
        # Config is set to INFO
        logger = StructuredLogger(logger_name, unstructured_log_config)

        logger.debug("This should not be logged")
        logger.info("This should be logged")

        log_file = log_dir / f"{logger_name}.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "This should not be logged" not in log_content
        assert "This should be logged" in log_content


class TestLoggerFactory:
    def setup_method(self):
        """Reset the factory before each test."""
        LoggerFactory._config = None
        LoggerFactory._loggers = {}

    def test_get_logger_unconfigured(self):
        """Test that getting a logger before configuration raises an error."""
        with pytest.raises(RuntimeError, match="must be configured"):
            LoggerFactory.get_logger("test")

    def test_get_logger_success(self, structured_log_config):
        """Test getting a logger after configuration."""
        LoggerFactory.configure(structured_log_config)
        logger = LoggerFactory.get_logger("test_logger")
        assert isinstance(logger, StructuredLogger)
        assert logger.logger.name == "test_logger"

    def test_get_logger_returns_same_instance(self, structured_log_config):
        """Test that subsequent calls for the same name return the same logger instance."""
        LoggerFactory.configure(structured_log_config)
        logger1 = LoggerFactory.get_logger("singleton")
        logger2 = LoggerFactory.get_logger("singleton")
        assert logger1 is logger2
