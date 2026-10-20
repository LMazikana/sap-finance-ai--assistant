
"""Provider-neutral model invocation contracts.

The finance assistant depends on these internal contracts rather than
depending directly on a specific model vendor or SDK.
"""

from __future__ import annotations

import time

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, runtime_checkable


# Restrict message roles to the standard chat roles currently needed
# by the finance assistant.
MessageRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One message sent to or received from a chat model."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        """Validate the role and message content."""

        allowed_roles = {
            "system",
            "user",
            "assistant",
        }

        if self.role not in allowed_roles:
            raise ValueError(
                f"Unsupported chat-message role: {self.role}"
            )

        if not self.content.strip():
            raise ValueError(
                "Chat-message content cannot be empty."
            )

    def to_api_dict(self) -> dict[str, str]:
        """Convert the message into an OpenAI-compatible dictionary."""

        return {
            "role": self.role,
            "content": self.content,
        }


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Provider-neutral request sent to a chat model."""

    messages: tuple[ChatMessage, ...]
    temperature: float = 0.1
    max_tokens: int = 500
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate required request parameters."""

        if not self.messages:
            raise ValueError(
                "A model request requires at least one message."
            )

        if not any(
            message.role == "user"
            for message in self.messages
        ):
            raise ValueError(
                "A model request requires a user message."
            )

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                "temperature must be between 0.0 and 2.0."
            )

        if self.max_tokens <= 0:
            raise ValueError(
                "max_tokens must be greater than zero."
            )

    def to_api_messages(self) -> list[dict[str, str]]:
        """Return messages in a provider-compatible structure."""

        return [
            message.to_api_dict()
            for message in self.messages
        ]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Normalized response returned by any model provider."""

    content: str
    provider: str
    model: str
    request_id: str
    finish_reason: str = "stop"
    usage: dict[str, int] = field(
        default_factory=dict
    )
    raw_response: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        """Validate the normalized provider response."""

        if not self.content.strip():
            raise ValueError(
                "Model-response content cannot be empty."
            )

        if not self.provider.strip():
            raise ValueError(
                "Model-response provider cannot be empty."
            )

        if not self.model.strip():
            raise ValueError(
                "Model-response model cannot be empty."
            )

        if not self.request_id.strip():
            raise ValueError(
                "Model-response request_id cannot be empty."
            )


class ModelProviderError(RuntimeError):
    """Base class for provider-related failures."""


class TransientModelProviderError(ModelProviderError):
    """Temporary failure that can normally be retried."""


class ModelProviderTimeoutError(
    TransientModelProviderError
):
    """Provider did not respond within the configured limit."""


class PermanentModelProviderError(ModelProviderError):
    """Failure that should not be retried automatically."""


class ProviderRetryExhaustedError(ModelProviderError):
    """All configured provider attempts failed."""

    def __init__(
        self,
        attempts: int,
        last_error: Exception,
    ) -> None:
        self.attempts = attempts
        self.last_error = last_error

        super().__init__(
            f"Provider failed after {attempts} attempts. "
            f"Last error: {last_error}"
        )


@runtime_checkable
class ModelProvider(Protocol):
    """Contract that every model-provider adapter must implement."""

    @property
    def provider_name(self) -> str:
        """Return a short provider identifier."""

        ...

    def generate(
        self,
        request: ModelRequest,
        timeout_seconds: float,
    ) -> ModelResponse:
        """Send one request and return a normalized response."""

        ...


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configuration for transient provider failures."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    maximum_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        """Validate retry settings."""

        if self.max_attempts < 1:
            raise ValueError(
                "max_attempts must be at least one."
            )

        if self.initial_delay_seconds < 0:
            raise ValueError(
                "initial_delay_seconds cannot be negative."
            )

        if self.backoff_multiplier < 1:
            raise ValueError(
                "backoff_multiplier must be at least 1."
            )

        if self.maximum_delay_seconds < 0:
            raise ValueError(
                "maximum_delay_seconds cannot be negative."
            )

    def delay_after_attempt(
        self,
        attempt_number: int,
    ) -> float:
        """Calculate exponential delay after a failed attempt."""

        calculated_delay = (
            self.initial_delay_seconds
            * (
                self.backoff_multiplier
                ** (attempt_number - 1)
            )
        )

        return min(
            calculated_delay,
            self.maximum_delay_seconds,
        )


@dataclass(frozen=True, slots=True)
class ProviderExecution:
    """Successful response plus retry and timing information."""

    response: ModelResponse
    attempts: int
    retry_delays_seconds: tuple[float, ...]
    total_latency_ms: float


def execute_with_retry(
    provider: ModelProvider,
    request: ModelRequest,
    *,
    retry_policy: RetryPolicy | None = None,
    timeout_seconds: float = 30.0,
    sleep_function: Callable[[float], None] = time.sleep,
    clock_function: Callable[[], float] = time.perf_counter,
) -> ProviderExecution:
    """Execute one provider request with bounded retries.

    Only TransientModelProviderError and its subclasses are retried.
    Permanent errors and programming errors are immediately propagated.
    """

    if timeout_seconds <= 0:
        raise ValueError(
            "timeout_seconds must be greater than zero."
        )

    policy = retry_policy or RetryPolicy()

    retry_delays: list[float] = []
    start_time = clock_function()

    for attempt_number in range(
        1,
        policy.max_attempts + 1,
    ):
        try:
            response = provider.generate(
                request=request,
                timeout_seconds=timeout_seconds,
            )

            total_latency_ms = round(
                (clock_function() - start_time) * 1000,
                3,
            )

            return ProviderExecution(
                response=response,
                attempts=attempt_number,
                retry_delays_seconds=tuple(
                    retry_delays
                ),
                total_latency_ms=total_latency_ms,
            )

        except TransientModelProviderError as error:
            final_attempt = (
                attempt_number
                >= policy.max_attempts
            )

            if final_attempt:
                raise ProviderRetryExhaustedError(
                    attempts=attempt_number,
                    last_error=error,
                ) from error

            delay_seconds = policy.delay_after_attempt(
                attempt_number
            )

            retry_delays.append(delay_seconds)
            sleep_function(delay_seconds)

    # This line is defensive. The loop should always return a response
    # or raise an exception.
    raise RuntimeError(
        "Provider execution ended unexpectedly."
    )
