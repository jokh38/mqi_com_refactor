# =====================================================================================
# Target File: src/utils/retry_policy.py
# Source Reference: Retry logic from various handlers
# =====================================================================================
"""!
@file retry_policy.py
@brief Provides a configurable retry policy and a circuit breaker pattern.
"""

import time
from typing import Callable, Any, Optional, Type, Union, List
from functools import wraps
from enum import Enum

from src.infrastructure.logging_handler import StructuredLogger
from src.domain.errors import RetryableError, CircuitBreakerOpenError


class RetryStrategy(Enum):
    """!
    @brief Defines different retry strategies.
    """
    FIXED_DELAY = "fixed_delay"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"


class RetryPolicy:
    """!
    @brief Configurable retry policy for handling transient failures.
    @details This class provides a reusable, configurable retry mechanism with different strategies.
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
        """!
        @brief Initializes the retry policy with configuration parameters.
        @param max_attempts: The maximum number of retry attempts.
        @param base_delay: The base delay between retries in seconds.
        @param max_delay: The maximum delay between retries in seconds.
        @param strategy: The retry strategy to use.
        @param retryable_exceptions: A list of exception types that should trigger retries.
        @param logger: A logger instance for retry events.
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.strategy = strategy
        self.retryable_exceptions = retryable_exceptions or [RetryableError]
        self.logger = logger

    def execute(self, func: Callable[..., Any], operation_name: str = "default_operation", context: Optional[dict] = None) -> Any:
        """!
        @brief Executes a function with retry logic.
        @param func: The function to execute.
        @param operation_name: The name of the operation for logging purposes.
        @param context: An optional dictionary of context data for logging.
        @return The result of the function if successful.
        @raises Exception: The last exception if all retries fail.
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
        """!
        @brief Determines if an exception should trigger a retry.
        @param exception: The exception that occurred.
        @param attempt: The current attempt number.
        @return True if a retry should be attempted, False otherwise.
        """
        if attempt >= self.max_attempts:
            return False

        for retryable in self.retryable_exceptions:
            if isinstance(exception, retryable):
                return True
        return False

    def _calculate_delay(self, attempt: int) -> float:
        """!
        @brief Calculates the delay before the next retry attempt.
        @param attempt: The current attempt number.
        @return The delay in seconds.
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
        """!
        @brief Logs a retry attempt with relevant context.
        @param exception: The exception that occurred.
        @param attempt: The current attempt number.
        @param delay: The delay before the next attempt.
        @param operation_name: The name of the operation being retried.
        @param context: An optional dictionary of context data.
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
    """!
    @brief Decorator for applying retry logic to functions.
    @param max_attempts: The maximum number of retry attempts.
    @param base_delay: The base delay between retries in seconds.
    @param strategy: The retry strategy to use.
    @param retryable_exceptions: A list of exception types that should trigger retries.
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
    """!
    @brief Implements the Circuit Breaker pattern for handling cascading failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
        logger: Optional[StructuredLogger] = None
    ):
        """!
        @brief Initializes the circuit breaker.
        @param failure_threshold: The number of failures required to open the circuit.
        @param timeout: The time in seconds to wait before moving to the half-open state.
        @param expected_exception: The type of exception to count as a failure.
        @param logger: A logger instance for circuit breaker events.
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exception = expected_exception
        self.logger = logger
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "closed"

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """!
        @brief Executes a function through the circuit breaker.
        @param func: The function to execute.
        @param *args: Positional arguments for the function.
        @param **kwargs: Keyword arguments for the function.
        @return The result of the function if successful.
        @raises CircuitBreakerOpenError: If the circuit is open.
        @raises Exception: The exception from the function if it fails.
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
        """!
        @brief Resets the circuit breaker to a closed state.
        """
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = None
        if self.logger:
            self.logger.info("Circuit breaker reset to closed state.")