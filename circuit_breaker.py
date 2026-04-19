"""
Circuit breaker pattern for handling service failures gracefully.

Implements state machine with Closed → Open → Half-Open → Closed transitions.
Integrates with cache fallback for resilience.
"""

import logging
import time
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Callable, Any, Dict, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes before closing from half-open
    timeout: int = 60  # Seconds before attempting recovery (half-open)
    expected_exception: type = Exception  # Exception type to catch


@dataclass
class CircuitBreakerMetrics:
    """Circuit breaker metrics."""
    failures: int = 0
    successes: int = 0
    total_requests: int = 0
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    last_failure: Optional[datetime] = None
    last_failure_reason: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker for handling service failures."""

    def __init__(self, config: CircuitBreakerConfig = None, name: str = "default"):
        """
        Initialize circuit breaker.

        Args:
            config: Circuit breaker configuration
            name: Circuit breaker name (for logging)
        """
        self.config = config or CircuitBreakerConfig()
        self.name = name
        self.state = CircuitState.CLOSED
        self.last_state_change = datetime.utcnow()
        self.metrics = CircuitBreakerMetrics()
        self._half_open_attempts = 0

    async def call(
        self,
        fn: Callable,
        *args,
        fallback: Optional[Callable] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            fn: Async function to execute
            args: Function positional arguments
            fallback: Fallback function if circuit open or error
            kwargs: Function keyword arguments

        Returns:
            Function result or fallback result
        """
        self.metrics.total_requests += 1

        # State machine transitions
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(f"Circuit {self.name} transitioned to HALF_OPEN")
            else:
                # Still open, use fallback
                if fallback:
                    logger.warning(f"Circuit {self.name} OPEN, using fallback")
                    return await fallback()
                raise CircuitBreakerOpenException(f"Circuit {self.name} is OPEN")

        # Attempt call
        try:
            result = await fn(*args, **kwargs)

            # Success
            if self.state == CircuitState.HALF_OPEN:
                self._half_open_attempts += 1
                if self._half_open_attempts >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    self._half_open_attempts = 0
                    logger.info(f"Circuit {self.name} CLOSED after recovery")

            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.metrics.failures = 0

            self.metrics.successes += 1
            return result

        except self.config.expected_exception as e:
            self.metrics.failures += 1
            self.metrics.last_failure = datetime.utcnow()
            self.metrics.last_failure_reason = str(e)

            logger.error(f"Circuit {self.name} failure: {e}")

            # Transition to open if threshold reached
            if self.metrics.failures >= self.config.failure_threshold:
                if self.state != CircuitState.OPEN:
                    self._transition_to(CircuitState.OPEN)
                    logger.warning(
                        f"Circuit {self.name} OPEN "
                        f"(failures: {self.metrics.failures})"
                    )

            # Use fallback on failure
            if fallback:
                logger.info(f"Circuit {self.name} failed, using fallback")
                return await fallback()

            raise

    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt reset."""
        timeout_elapsed = (
            datetime.utcnow() - self.last_state_change
        ).total_seconds() >= self.config.timeout
        return timeout_elapsed

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to new state."""
        old_state = self.state
        self.state = new_state
        self.last_state_change = datetime.utcnow()

        # Record state change
        self.metrics.state_changes.append({
            "from": old_state.value,
            "to": new_state.value,
            "timestamp": self.last_state_change.isoformat(),
            "failures": self.metrics.failures,
            "successes": self.metrics.successes,
        })

    def reset(self) -> None:
        """Manually reset circuit breaker."""
        self._transition_to(CircuitState.CLOSED)
        self.metrics.failures = 0
        self.metrics.successes = 0
        self._half_open_attempts = 0
        logger.info(f"Circuit {self.name} manually reset")

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "metrics": {
                "failures": self.metrics.failures,
                "successes": self.metrics.successes,
                "total_requests": self.metrics.total_requests,
                "last_failure": self.metrics.last_failure.isoformat() if self.metrics.last_failure else None,
                "last_failure_reason": self.metrics.last_failure_reason,
            },
            "state_changes": self.metrics.state_changes[-10:],  # Last 10 changes
        }


class CircuitBreakerPool:
    """Pool of circuit breakers for different services."""

    def __init__(self):
        """Initialize circuit breaker pool."""
        self._breakers: Dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        config: CircuitBreakerConfig = None,
    ) -> CircuitBreaker:
        """
        Get or create circuit breaker.

        Args:
            name: Circuit breaker name
            config: Configuration if creating new

        Returns:
            Circuit breaker instance
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(config, name)
        return self._breakers[name]

    async def call(
        self,
        name: str,
        fn: Callable,
        *args,
        fallback: Optional[Callable] = None,
        config: Optional[CircuitBreakerConfig] = None,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker.

        Args:
            name: Circuit breaker name
            fn: Function to execute
            args: Positional arguments
            fallback: Fallback function
            config: Configuration if creating new
            kwargs: Keyword arguments

        Returns:
            Function result or fallback result
        """
        breaker = self.get_or_create(name, config)
        return await breaker.call(fn, *args, fallback=fallback, **kwargs)

    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
        }

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()
        logger.info("All circuit breakers reset")


class CircuitBreakerOpenException(Exception):
    """Exception when circuit breaker is open."""
    pass


# Retry with exponential backoff
@dataclass
class RetryConfig:
    """Retry configuration."""
    max_attempts: int = 3
    initial_delay: float = 0.1  # seconds
    max_delay: float = 10.0  # seconds
    exponential_base: float = 2.0


class RetryPolicy:
    """Retry policy with exponential backoff."""

    def __init__(self, config: RetryConfig = None):
        """Initialize retry policy."""
        self.config = config or RetryConfig()

    async def execute(
        self,
        fn: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with retries.

        Args:
            fn: Async function to execute
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Function result
        """
        attempt = 0
        delay = self.config.initial_delay

        while attempt < self.config.max_attempts:
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                attempt += 1
                if attempt >= self.config.max_attempts:
                    logger.error(f"Max retries exceeded: {e}")
                    raise

                logger.warning(f"Attempt {attempt} failed, retrying in {delay}s: {e}")
                await asyncio.sleep(delay)

                # Exponential backoff
                delay = min(
                    delay * self.config.exponential_base,
                    self.config.max_delay
                )


import asyncio
