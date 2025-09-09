# =====================================================================================
# Target File: src/domain/errors.py
# Source Reference: src/error_categorization.py
# =====================================================================================
"""!
@file errors.py
@brief Defines custom exception classes for the application.
"""

class MQIError(Exception):
    """!
    @brief Base exception class for all MQI application errors.
    """
    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

class DatabaseError(MQIError):
    """!
    @brief Exception raised for database-related errors.
    """
    pass

class GpuResourceError(MQIError):
    """!
    @brief Exception raised for GPU resource management errors.
    """
    pass

class WorkflowError(MQIError):
    """!
    @brief Exception raised for workflow execution errors.
    """
    def __init__(self, message: str, step: str = None, case_id: str = None, context: dict = None):
        super().__init__(message, context)
        self.step = step
        self.case_id = case_id

class ConfigurationError(MQIError):
    """!
    @brief Exception raised for configuration-related errors.
    """
    pass

class ProcessingError(MQIError):
    """!
    @brief Exception raised for case processing errors.
    """
    def __init__(self, message: str, case_id: str = None, context: dict = None):
        super().__init__(message, context)
        self.case_id = case_id

class ValidationError(MQIError):
    """!
    @brief Exception raised for input validation errors.
    """
    pass

class RetryableError(MQIError):
    """!
    @brief Exception raised for errors that can be safely retried.
    """
    pass

class CircuitBreakerOpenError(MQIError):
    """!
    @brief Exception raised when the circuit breaker is open.
    """
    pass