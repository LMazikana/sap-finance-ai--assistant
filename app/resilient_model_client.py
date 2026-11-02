"""Resilient and auditable model API client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import time
from typing import Any, Callable
from uuid import uuid4


# These failures are commonly temporary and can be retried.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# These keys must never appear in an audit event with their real values.
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
}


@dataclass(frozen=True)
class TransportResponse:
    """Provider-neutral representation of an HTTP response."""

    status_code: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiCallResult:
    """Normalized result returned to the finance application."""

    ok: bool
    request_id: str
    attempts: int
    status_code: int | None
    response: dict[str, Any] | None
    error_code: str | None
    audit_event: dict[str, Any]


def redact_sensitive_values(value: Any) -> Any:
    """
    Recursively replace credential-like values before audit logging.

    The application can still use the original metadata for its request,
    but the audit event receives only the redacted copy.
    """

    if isinstance(value, dict):
        redacted = {}

        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")

            sensitive_suffix = normalized_key.endswith(
                ("_token", "_secret", "_password", "_api_key")
            )

            if normalized_key in SENSITIVE_KEYS or sensitive_suffix:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_values(item)

        return redacted

    if isinstance(value, (list, tuple)):
        return [redact_sensitive_values(item) for item in value]

    return value


class ScriptedTransport:
    """
    Deterministic fake API transport used for notebook testing.

    Each scripted step is either a TransportResponse or an exception.
    No real provider, internet connection or API credential is required.
    """

    def __init__(self, steps: list[Any]):
        self.steps = list(steps)
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> TransportResponse:
        self.calls.append(
            {
                "payload": payload,
                "headers": headers.copy(),
            }
        )

        if not self.steps:
            raise RuntimeError("The scripted transport has no remaining response.")

        next_step = self.steps.pop(0)

        if isinstance(next_step, BaseException):
            raise next_step

        return next_step


class ResilientModelClient:
    """
    Call a model provider through an injected transport function.

    A real implementation can replace ScriptedTransport with an adapter
    for Databricks Model Serving or SAP Generative AI Hub.
    """

    def __init__(
        self,
        transport: Callable[
            [dict[str, Any], dict[str, str]],
            TransportResponse,
        ],
        max_attempts: int = 3,
        base_delay_seconds: float = 0.25,
        sleep_function: Callable[[float], None] = time.sleep,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1.")

        self.transport = transport
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.sleep_function = sleep_function

    def _retry_delay(
        self,
        attempt: int,
        response: TransportResponse | None = None,
    ) -> float:
        """
        Prefer the provider's Retry-After value when supplied.

        Otherwise use exponential backoff:
        base delay, 2 × base delay, 4 × base delay, and so forth.
        """

        if response is not None:
            retry_after = response.headers.get("Retry-After")

            if retry_after is not None:
                try:
                    return max(0.0, float(retry_after))
                except ValueError:
                    pass

        return self.base_delay_seconds * (2 ** (attempt - 1))

    def _build_result(
        self,
        *,
        ok: bool,
        request_id: str,
        attempts: int,
        status_code: int | None,
        response_body: dict[str, Any] | None,
        error_code: str | None,
        user_role: str,
        question: str,
        approved_context: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> ApiCallResult:
        """
        Build a result and its privacy-aware audit event.

        The raw question and retrieved policy text are deliberately excluded.
        A SHA-256 hash supports correlation without storing the question.
        """

        policy_ids = sorted(
            {
                str(item["policy_id"])
                for item in approved_context
                if item.get("policy_id")
            }
        )

        audit_event = {
            "event_type": "model_api_call",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "user_role": user_role,
            "question_sha256": sha256(
                question.encode("utf-8")
            ).hexdigest(),
            "policy_ids": policy_ids,
            "attempts": attempts,
            "status_code": status_code,
            "outcome": "success" if ok else "failure",
            "error_code": error_code,
            "metadata": redact_sensitive_values(metadata),
        }

        return ApiCallResult(
            ok=ok,
            request_id=request_id,
            attempts=attempts,
            status_code=status_code,
            response=response_body if ok else None,
            error_code=error_code,
            audit_event=audit_event,
        )

    def invoke(
        self,
        *,
        question: str,
        user_role: str,
        approved_context: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ApiCallResult:
        """Invoke the provider with bounded retry behavior."""

        metadata = metadata or {}
        request_id = request_id or str(uuid4())

        # The same identifiers are reused for every retry of one logical call.
        headers = {
            "X-Request-ID": request_id,
            "Idempotency-Key": request_id,
        }

        payload = {
            "question": question,
            "user_role": user_role,
            "approved_context": approved_context,
            "metadata": metadata,
        }

        for attempt in range(1, self.max_attempts + 1):
            try:
                provider_response = self.transport(payload, headers)

            except (TimeoutError, ConnectionError) as error:
                if attempt < self.max_attempts:
                    delay = self._retry_delay(attempt)
                    self.sleep_function(delay)
                    continue

                return self._build_result(
                    ok=False,
                    request_id=request_id,
                    attempts=attempt,
                    status_code=None,
                    response_body=None,
                    error_code=type(error).__name__.lower(),
                    user_role=user_role,
                    question=question,
                    approved_context=approved_context,
                    metadata=metadata,
                )

            status_code = provider_response.status_code

            if 200 <= status_code < 300:
                return self._build_result(
                    ok=True,
                    request_id=request_id,
                    attempts=attempt,
                    status_code=status_code,
                    response_body=provider_response.body,
                    error_code=None,
                    user_role=user_role,
                    question=question,
                    approved_context=approved_context,
                    metadata=metadata,
                )

            retryable = status_code in RETRYABLE_STATUS_CODES

            if retryable and attempt < self.max_attempts:
                delay = self._retry_delay(attempt, provider_response)
                self.sleep_function(delay)
                continue

            return self._build_result(
                ok=False,
                request_id=request_id,
                attempts=attempt,
                status_code=status_code,
                response_body=None,
                error_code=f"http_{status_code}",
                user_role=user_role,
                question=question,
                approved_context=approved_context,
                metadata=metadata,
            )

        raise AssertionError("The retry loop ended unexpectedly.")
