import pytest
from src.domain.errors import (
    MQIError,
    DatabaseError,
    GpuResourceError,
    WorkflowError,
    ConfigurationError,
    ProcessingError,
    ValidationError,
    RetryableError,
    CircuitBreakerOpenError,
)


def test_mqi_error():
    """
    Tests that MQIError can be raised and stores message and context.
    """
    message = "A generic MQI error occurred."
    context = {"key": "value"}
    with pytest.raises(MQIError) as excinfo:
        raise MQIError(message, context=context)

    assert excinfo.value.message == message
    assert excinfo.value.context == context
    assert str(excinfo.value) == message


def test_mqi_error_no_context():
    """
    Tests that MQIError can be raised without a context.
    """
    message = "An error without context."
    with pytest.raises(MQIError) as excinfo:
        raise MQIError(message)

    assert excinfo.value.message == message
    assert excinfo.value.context == {}  # Should default to an empty dict
    assert str(excinfo.value) == message


def test_database_error():
    """
    Tests that DatabaseError can be raised.
    """
    message = "A database error."
    with pytest.raises(DatabaseError) as excinfo:
        raise DatabaseError(message)

    assert excinfo.value.message == message
    assert issubclass(DatabaseError, MQIError)


def test_gpu_resource_error():
    """
    Tests that GpuResourceError can be raised.
    """
    message = "A GPU resource error."
    with pytest.raises(GpuResourceError) as excinfo:
        raise GpuResourceError(message)

    assert excinfo.value.message == message
    assert issubclass(GpuResourceError, MQIError)


def test_workflow_error():
    """
    Tests that WorkflowError can be raised and stores its specific attributes.
    """
    message = "A workflow error."
    step = "processing"
    case_id = "case-123"
    context = {"detail": "something went wrong"}

    with pytest.raises(WorkflowError) as excinfo:
        raise WorkflowError(
            message, step=step, case_id=case_id, context=context
        )

    assert excinfo.value.message == message
    assert excinfo.value.step == step
    assert excinfo.value.case_id == case_id
    assert excinfo.value.context == context
    assert issubclass(WorkflowError, MQIError)


def test_configuration_error():
    """
    Tests that ConfigurationError can be raised.
    """
    message = "A configuration error."
    with pytest.raises(ConfigurationError) as excinfo:
        raise ConfigurationError(message)

    assert excinfo.value.message == message
    assert issubclass(ConfigurationError, MQIError)


def test_processing_error():
    """
    Tests that ProcessingError can be raised and stores its attributes.
    """
    message = "A processing error."
    case_id = "case-456"
    context = {"output": "failed"}

    with pytest.raises(ProcessingError) as excinfo:
        raise ProcessingError(message, case_id=case_id, context=context)

    assert excinfo.value.message == message
    assert excinfo.value.case_id == case_id
    assert excinfo.value.context == context
    assert issubclass(ProcessingError, MQIError)


def test_validation_error():
    """
    Tests that ValidationError can be raised.
    """
    message = "A validation error."
    with pytest.raises(ValidationError) as excinfo:
        raise ValidationError(message)

    assert excinfo.value.message == message
    assert issubclass(ValidationError, MQIError)


def test_retryable_error():
    """
    Tests that RetryableError can be raised.
    """
    message = "A retryable error."
    with pytest.raises(RetryableError) as excinfo:
        raise RetryableError(message)

    assert excinfo.value.message == message
    assert issubclass(RetryableError, MQIError)


def test_circuit_breaker_open_error():
    """
    Tests that CircuitBreakerOpenError can be raised.
    """
    message = "Circuit breaker is open."
    with pytest.raises(CircuitBreakerOpenError) as excinfo:
        raise CircuitBreakerOpenError(message)

    assert excinfo.value.message == message
    assert issubclass(CircuitBreakerOpenError, MQIError)
