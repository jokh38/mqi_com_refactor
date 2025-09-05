import pytest
import json
import logging
from io import StringIO
from pathlib import Path

from src.infrastructure.logging_handler import LoggerFactory, StructuredLogger
from src.config.settings import LoggingConfig

@pytest.fixture(autouse=True)
def reset_logger_factory():
    """Reset the LoggerFactory singleton before and after each test."""
    LoggerFactory._config = None
    LoggerFactory._loggers = {}
    yield
    LoggerFactory._config = None
    LoggerFactory._loggers = {}

@pytest.fixture
def structured_log_config(tmp_path: Path) -> LoggingConfig:
    """Fixture for a structured logging configuration."""
    return LoggingConfig(
        log_dir=tmp_path,
        log_level="DEBUG",
        structured_logging=True,
        max_file_size=1,
        backup_count=1
    )

@pytest.fixture
def plain_log_config(tmp_path: Path) -> LoggingConfig:
    """Fixture for a plain text logging configuration."""
    return LoggingConfig(
        log_dir=tmp_path,
        log_level="DEBUG",
        structured_logging=False,
        max_file_size=1,
        backup_count=1
    )

def test_logger_factory_unconfigured():
    """Test that getting a logger before configuration raises an error."""
    with pytest.raises(RuntimeError, match="LoggerFactory must be configured"):
        LoggerFactory.get_logger("test")

def test_logger_factory_configure_and_get(structured_log_config: LoggingConfig):
    """Test configuring the factory and getting a logger."""
    LoggerFactory.configure(structured_log_config)
    logger = LoggerFactory.get_logger("test_logger")

    assert isinstance(logger, StructuredLogger)
    assert logger.logger.name == "test_logger"

    # Getting the same logger should return the same instance
    logger2 = LoggerFactory.get_logger("test_logger")
    assert logger is logger2

def test_plain_text_logging(plain_log_config: LoggingConfig):
    """Test that logging in plain text format works correctly."""
    LoggerFactory.configure(plain_log_config)
    logger = LoggerFactory.get_logger("plain_test")

    # Capture logs
    log_stream = StringIO()
    # Create a handler with the correct formatter
    handler = logging.StreamHandler(log_stream)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)

    logger.logger.handlers = [handler]

    logger.info("This is an info message.")

    log_output = log_stream.getvalue()
    assert "INFO" in log_output
    assert "This is an info message." in log_output
    # Check that it's not JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(log_output.strip())

def test_structured_logging(structured_log_config: LoggingConfig):
    """Test that logging in structured JSON format works correctly."""
    LoggerFactory.configure(structured_log_config)
    logger = LoggerFactory.get_logger("structured_test")

    log_stream = StringIO()
    # Get the correct formatter from the logger
    handler = logging.StreamHandler(log_stream)
    formatter = logger._create_json_formatter()
    handler.setFormatter(formatter)
    logger.logger.handlers = [handler]

    context = {"user_id": 123, "request_id": "abc-123"}
    logger.warning("This is a warning.", context=context)

    log_output = log_stream.getvalue()
    log_json = json.loads(log_output)

    assert log_json['level'] == 'WARNING'
    assert log_json['logger'] == 'structured_test'
    assert log_json['message'] == 'This is a warning.'
    assert log_json['context']['user_id'] == 123
    assert log_json['context']['request_id'] == "abc-123"

def test_exception_logging(structured_log_config: LoggingConfig):
    """Test that exception information is included in structured logs."""
    LoggerFactory.configure(structured_log_config)
    logger = LoggerFactory.get_logger("exception_test")

    log_stream = StringIO()
    # Get the correct formatter from the logger
    handler = logging.StreamHandler(log_stream)
    formatter = logger._create_json_formatter()
    handler.setFormatter(formatter)
    logger.logger.handlers = [handler]

    try:
        raise ValueError("This is a test exception")
    except ValueError:
        logger.error("An exception occurred.", context={"extra": "info"}, exc_info=True)

    log_output = log_stream.getvalue()
    log_json = json.loads(log_output)

    assert log_json['level'] == 'ERROR'
    assert log_json['message'] == 'An exception occurred.'
    assert 'exception' in log_json
    assert "ValueError: This is a test exception" in log_json['exception']
    assert log_json['context']['extra'] == 'info'

def test_log_levels(plain_log_config: LoggingConfig):
    """Test that log levels are respected."""
    plain_log_config.log_level = "INFO"
    LoggerFactory.configure(plain_log_config)
    logger = LoggerFactory.get_logger("levels_test")

    log_stream = StringIO()
    logger.logger.handlers = [logging.StreamHandler(log_stream)]

    logger.debug("This should not be logged.")
    logger.info("This should be logged.")

    log_output = log_stream.getvalue()

    assert "This should not be logged." not in log_output
    assert "This should be logged." in log_output
