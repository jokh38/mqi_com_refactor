# =====================================================================================
# Target File: src/domain/errors.py
# Source Reference: src/error_categorization.py
# =====================================================================================

class MQIError(Exception):
    """
    Base exception class for all MQI application errors.
    FROM: Base error handling patterns from original codebase.
    """
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

class DatabaseError(MQIError):
    """
    Exception raised for database-related errors.
    FROM: Database error handling in original database_handler.py.
    """
    pass

class GpuResourceError(MQIError):
    """
    Exception raised for GPU resource management errors.
    FROM: GPU allocation and monitoring errors from original codebase.
    """
    pass

class WorkflowError(MQIError):
    """
    Exception raised for workflow execution errors.
    FROM: Workflow step execution errors from original workflow_manager.py.
    """
    def __init__(self, message: str, step: str = None, case_id: str = None, context: dict = None):
        super().__init__(message, context)
        self.step = step
        self.case_id = case_id

class ConfigurationError(MQIError):
    """
    Exception raised for configuration-related errors.
    FROM: Configuration validation errors from original config.py.
    """
    pass

class ProcessingError(MQIError):
    """
    Exception raised for case processing errors.
    FROM: Processing errors from original handler classes.
    """
    def __init__(self, message: str, case_id: str = None, context: dict = None):
        super().__init__(message, context)
        self.case_id = case_id

class ValidationError(MQIError):
    """
    Exception raised for input validation errors.
    FROM: File and path validation errors from original codebase.
    """
    pass

class RetryableError(MQIError):
    """
    Exception raised for errors that can be safely retried.
    FROM: Conceptual need from the new RetryPolicy utility.
    """
    pass

class CircuitBreakerOpenError(MQIError):
    """
    Exception raised when the circuit breaker is open.
    """
    pass