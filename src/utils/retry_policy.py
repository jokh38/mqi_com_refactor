# =====================================================================================
# Target File: src/utils/retry_policy.py
# Source Reference: Retry logic from various handlers
# =====================================================================================
"""Provides a configurable retry policy and a circuit breaker pattern."""

import time
from typing import Callable, Any, Optional, Type, Union, List
from functools import wraps
from enum import Enum

from src.infrastructure.logging_handler import StructuredLogger
from src.domain.errors import RetryableError, CircuitBreakerOpenError


class RetryStrategy(Enum):
    """Defines different retry strategies."""
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"


class RetryPolicy:
    """Configurable retry policy for handling transient failures.

    This class provides a reusable, configurable retry mechanism with different strategies.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
        logger: Optional[StructuredLogger] = None
    ):
        """Initializes the retry policy with configuration parameters.

        Args:
            max_attempts (int, optional): The maximum number of retry attempts. Defaults to 3.
            base_delay (float, optional): The base delay between retries in seconds. Defaults to 1.0.
            max_delay (float, optional): The maximum delay between retries in seconds. Defaults to 60.0.
            strategy (RetryStrategy, optional): The retry strategy to use. Defaults to RetryStrategy.EXPONENTIAL_BACKOFF.
            retryable_exceptions (Optional[List[Type[Exception]]], optional): A list of exception types that should trigger retries. Defaults to None.
            logger (Optional[StructuredLogger], optional): A logger instance for retry events. Defaults to None.
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.strategy = strategy
        self.retryable_exceptions = retryable_exceptions or [RetryableError]
        self.logger = logger

    def execute(self, func: Callable[..., Any], operation_name: str = "default_operation", context: Optional[dict] = None) -> Any:
        """Executes a function with retry logic.

        Args:
            func (Callable[..., Any]): The function to execute.
            operation_name (str, optional): The name of the operation for logging purposes. Defaults to "default_operation".
            context (Optional[dict], optional): An optional dictionary of context data for logging. Defaults to None.

        Raises:
            Exception: The last exception if all retries fail.

        Returns:
            Any: The result of the function if successful.
        """
        last_exception = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                return func()
            except Exception as e:
                last_exception = e
                if not self._should_retry(e, attempt):
                    raise e

                delay = self._calculate_delay(attempt)
                self._log_retry_attempt(e, attempt, delay, operation_name, context)
                time.sleep(delay)

        raise last_exception

    def _should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determines if an exception should trigger a retry.

        Args:
            exception (Exception): The exception that occurred.
            attempt (int): The current attempt number.

        Returns:
            bool: True if a retry should be attempted, False otherwise.
        """
        if attempt >= self.max_attempts:
            return False

        for retryable in self.retryable_exceptions:
            if isinstance(exception, retryable):
                return True
        return False

    def _calculate_delay(self, attempt: int) -> float:
        """Calculates the delay before the next retry attempt.

        Args:
            attempt (int): The current attempt number.

        Returns:
            float: The delay in seconds.
        """
        if self.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.base_delay
        elif self.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay * (2 ** (attempt - 1))
        elif self.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.base_delay * attempt
        else:
            delay = self.base_delay

        return min(delay, self.max_delay)

    def _log_retry_attempt(self, exception: Exception, attempt: int, delay: float, operation_name: str, context: Optional[dict]) -> None:
        """Logs a retry attempt with relevant context.

        Args:
            exception (Exception): The exception that occurred.
            attempt (int): The current attempt number.
            delay (float): The delay before the next attempt.
            operation_name (str): The name of the operation being retried.
            context (Optional[dict]): An optional dictionary of context data.
        """
        if self.logger:
            log_context = {
                "operation": operation_name,
                "exception": str(exception),
                "attempt": attempt,
                "max_attempts": self.max_attempts,
                "delay": delay,
            }
            if context:
                log_context.update(context)
            self.logger.warning("Retrying operation", log_context)


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
    retryable_exceptions: Optional[List[Type[Exception]]] = None
):
    """Decorator for applying retry logic to functions.

    Args:
        max_attempts (int, optional): The maximum number of retry attempts. Defaults to 3.
        base_delay (float, optional): The base delay between retries in seconds. Defaults to 1.0.
        strategy (RetryStrategy, optional): The retry strategy to use. Defaults to RetryStrategy.EXPONENTIAL_BACKOFF.
        retryable_exceptions (Optional[List[Type[Exception]]], optional): A list of exception types that should trigger retries. Defaults to None.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            policy = RetryPolicy(
                max_attempts=max_attempts,
                base_delay=base_delay,
                strategy=strategy,
                retryable_exceptions=retryable_exceptions
            )
            return policy.execute(lambda: func(*args, **kwargs))
        return wrapper
    return decorator


class CircuitBreaker:
    """Implements the Circuit Breaker pattern for handling cascading failures."""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
        logger: Optional[StructuredLogger] = None
    ):
        """Initializes the circuit breaker.

        Args:
            failure_threshold (int, optional): The number of failures required to open the circuit. Defaults to 5.
            timeout (float, optional): The time in seconds to wait before moving to the half-open state. Defaults to 60.0.
            expected_exception (Type[Exception], optional): The type of exception to count as a failure. Defaults to Exception.
            logger (Optional[StructuredLogger], optional): A logger instance for circuit breaker events. Defaults to None.
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.logger = logger
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Executes a function through the circuit breaker.

        Args:
            func (Callable[..., Any]): The function to execute.

        Raises:
            CircuitBreakerOpenError: If the circuit is open.
            Exception: The exception from the function if it fails.

        Returns:
            Any: The result of the function if successful.
        """
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "half-open"
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open.")

        try:
            result = func(*args, **kwargs)
            self.reset()
            return result
        except self.expected_exception as e:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                self.last_failure_time = time.time()
                if self.logger:
                    self.logger.error("Circuit breaker opened.", {"threshold": self.failure_threshold})
            raise e

    def reset(self):
        """Resets the circuit breaker to a closed state."""
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = None
        if self.logger:
            self.logger.info("Circuit breaker reset to closed state.")