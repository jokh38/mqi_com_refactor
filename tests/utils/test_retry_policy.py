import pytest
import time
from unittest.mock import MagicMock, patch

from src.utils.retry_policy import RetryPolicy, RetryStrategy, retry
from src.domain.errors import RetryableError, MQIError, CircuitBreakerOpenError
from src.utils.retry_policy import CircuitBreaker


@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    return MagicMock()


class TestRetryPolicy:
    def test_execute_success_first_try(self, mock_logger):
        """Test that the function is executed successfully on the first attempt."""
        policy = RetryPolicy(logger=mock_logger)
        func = MagicMock(return_value="success")
        result = policy.execute(func, "test_op")
        assert result == "success"
        func.assert_called_once()
        mock_logger.warning.assert_not_called()

    def test_execute_retries_on_retryable_error(self, mock_logger):
        """Test that the function is retried on a retryable exception."""
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, logger=mock_logger)
        func = MagicMock(side_effect=[RetryableError("fail"), "success"])

        with patch("time.sleep") as mock_sleep:
            result = policy.execute(func, "test_op")

        assert result == "success"
        assert func.call_count == 2
        mock_sleep.assert_called_once()
        mock_logger.warning.assert_called_once()

    def test_execute_exhausts_retries_and_raises(self, mock_logger):
        """Test that the last exception is raised after all retries are exhausted."""
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, logger=mock_logger)
        func = MagicMock(side_effect=RetryableError("permanent fail"))

        with pytest.raises(RetryableError, match="permanent fail"):
            with patch("time.sleep"):
                policy.execute(func, "test_op")

        assert func.call_count == 3
        assert mock_logger.warning.call_count == 2

    def test_execute_does_not_retry_on_non_retryable_error(self, mock_logger):
        """Test that non-retryable exceptions are not retried."""
        policy = RetryPolicy(max_attempts=3, logger=mock_logger)
        func = MagicMock(side_effect=MQIError("non-retryable"))

        with pytest.raises(MQIError, match="non-retryable"):
            policy.execute(func, "test_op")

        func.assert_called_once()
        mock_logger.warning.assert_not_called()

    @pytest.mark.parametrize("strategy, expected_delays", [
        (RetryStrategy.FIXED_DELAY, [0.1, 0.1]),
        (RetryStrategy.EXPONENTIAL_BACKOFF, [0.1, 0.2]),
        (RetryStrategy.LINEAR_BACKOFF, [0.1, 0.2]),
    ])
    def test_retry_strategies(self, mock_logger, strategy, expected_delays):
        """Test different retry delay strategies."""
        policy = RetryPolicy(max_attempts=3, base_delay=0.1, strategy=strategy, logger=mock_logger)
        func = MagicMock(side_effect=[RetryableError("fail"), RetryableError("fail"), "success"])

        with patch("time.sleep") as mock_sleep:
            policy.execute(func, "test_op")

        assert mock_sleep.call_count == len(expected_delays)
        for i, delay in enumerate(expected_delays):
            assert mock_sleep.call_args_list[i][0][0] == pytest.approx(delay)

    def test_max_delay(self, mock_logger):
        """Test that the delay does not exceed max_delay."""
        policy = RetryPolicy(
            max_attempts=5,
            base_delay=1,
            max_delay=3,
            strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
            logger=mock_logger
        )
        # Delays would be: 1, 2, 4, 8 -> capped at 3 -> 1, 2, 3, 3
        expected_delays = [1, 2, 3, 3]
        func = MagicMock(side_effect=[RetryableError("fail")] * 4 + ["success"])

        with patch("time.sleep") as mock_sleep:
            policy.execute(func, "test_op")

        for i, delay in enumerate(expected_delays):
            assert mock_sleep.call_args_list[i][0][0] == pytest.approx(delay)


@retry(max_attempts=3, base_delay=0.01)
def decorated_function_retryable_fail():
    """A decorated function that always fails with a retryable error."""
    raise RetryableError("fail")

@retry(max_attempts=3, base_delay=0.01)
def decorated_function_non_retryable_fail():
    """A decorated function that always fails with a non-retryable error."""
    raise MQIError("fail")

class TestRetryDecorator:
    @patch("time.sleep", return_value=None)
    def test_decorator_retries_and_fails(self, mock_sleep):
        """Test that the decorator retries and eventually fails."""
        with pytest.raises(RetryableError):
            decorated_function_retryable_fail()
        # The decorator creates its own policy, so we can't easily check call count.
        # But we can check that it slept twice (for 3 attempts).
        assert mock_sleep.call_count == 2

    def test_decorator_no_retry_on_non_retryable(self):
        """Test that the decorator does not retry on non-retryable errors."""
        with pytest.raises(MQIError):
            decorated_function_non_retryable_fail()

    def test_decorator_success(self):
        """Test that the decorator returns the value on success."""
        mock_func = MagicMock(side_effect=[RetryableError("fail"), "success"])
        decorated = retry(max_attempts=3, base_delay=0.01)(mock_func)

        with patch("time.sleep"):
            result = decorated()

        assert result == "success"
        assert mock_func.call_count == 2


class TestCircuitBreaker:
    def test_closed_state_success(self, mock_logger):
        """Test that in a closed state, a successful call is passed through."""
        breaker = CircuitBreaker(logger=mock_logger)
        func = MagicMock(return_value="success")
        result = breaker.call(func)
        assert result == "success"
        func.assert_called_once()
        assert breaker.state == "closed"

    def test_closed_state_failure_increases_count(self, mock_logger):
        """Test that failures in a closed state increase the failure count."""
        breaker = CircuitBreaker(failure_threshold=3, logger=mock_logger)
        func = MagicMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            breaker.call(func)

        assert breaker.failure_count == 1
        assert breaker.state == "closed"

    def test_transitions_to_open_state(self, mock_logger):
        """Test that the breaker opens after the failure threshold is reached."""
        breaker = CircuitBreaker(failure_threshold=2, logger=mock_logger)
        func = MagicMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            breaker.call(func)
        with pytest.raises(ValueError):
            breaker.call(func)

        assert breaker.state == "open"
        mock_logger.error.assert_called_with("Circuit breaker opened.", {"threshold": 2})

    def test_open_state_blocks_calls(self, mock_logger):
        """Test that the breaker blocks calls when in the open state."""
        breaker = CircuitBreaker(failure_threshold=1, logger=mock_logger)
        func = MagicMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            breaker.call(func)

        assert breaker.state == "open"

        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(func)

        func.assert_called_once() # Should not be called again

    @patch("time.time")
    def test_half_open_to_closed_on_success(self, mock_time, mock_logger):
        """Test that a successful call in half-open state closes the breaker."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=10, logger=mock_logger)

        # 1. Open the breaker
        mock_time.return_value = 100
        with pytest.raises(ValueError):
            breaker.call(MagicMock(side_effect=ValueError("fail")))
        assert breaker.state == "open"

        # 2. Move time forward to allow transition to half-open
        mock_time.return_value = 111

        # 3. Make a successful call
        successful_func = MagicMock(return_value="success")
        result = breaker.call(successful_func)

        # Assertions
        assert result == "success"
        assert breaker.state == "closed"
        assert breaker.failure_count == 0
        mock_logger.info.assert_called_with("Circuit breaker reset to closed state.")

    @patch("time.time")
    def test_half_open_to_open_on_failure(self, mock_time, mock_logger):
        """Test that a failed call in half-open state re-opens the breaker."""
        breaker = CircuitBreaker(failure_threshold=1, timeout=10, logger=mock_logger)

        # 1. Open the breaker
        mock_time.return_value = 100
        with pytest.raises(ValueError):
            breaker.call(MagicMock(side_effect=ValueError("fail1")))
        assert breaker.state == "open"

        # 2. Move time forward to allow transition to half-open
        mock_time.return_value = 111

        # 3. Make a failing call
        failing_func = MagicMock(side_effect=ValueError("fail2"))
        with pytest.raises(ValueError, match="fail2"):
            breaker.call(failing_func)

        # Assertions
        assert breaker.state == "open"
        # The failure count increments with each failure.
        assert breaker.failure_count == 2
