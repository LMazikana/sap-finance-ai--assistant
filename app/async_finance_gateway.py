"""Asynchronous gateway for governed Finance model requests."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Awaitable, Callable
import asyncio
import hashlib
import json


class AsyncFinanceGateway:
    """Control asynchronous provider access."""

    def __init__(
        self,
        provider: Callable[[dict], Awaitable[dict]],
        timeout_seconds: float,
        max_concurrency: int,
        audit_path: Path,
    ):
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be greater than zero."
            )

        if max_concurrency <= 0:
            raise ValueError(
                "max_concurrency must be greater than zero."
            )

        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.audit_path = Path(audit_path)

        self._semaphore = asyncio.Semaphore(
            max_concurrency
        )

        self._state_lock = asyncio.Lock()
        self._audit_lock = asyncio.Lock()

        self._completed_results = {}
        self._inflight_tasks = {}

    @property
    def cache_size(self) -> int:
        """Return the number of successful cached operations."""

        return len(self._completed_results)

    @property
    def inflight_count(self) -> int:
        """Return the current number of in-flight operations."""

        return len(self._inflight_tasks)

    @staticmethod
    def _hash_key(idempotency_key: str) -> str:
        """Hash an idempotency key before audit logging."""

        return hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()

    async def _write_audit(
        self,
        event_type: str,
        request: dict,
        **metadata,
    ) -> None:
        """
        Append one audit event.

        The raw question and raw idempotency key are not stored.
        """

        event = {
            "timestamp_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "event_type": event_type,
            "request_id": request.get(
                "request_id"
            ),
            "user_role": request.get(
                "user_role"
            ),
            "business_unit": request.get(
                "business_unit"
            ),
            "idempotency_key_sha256": self._hash_key(
                request["idempotency_key"]
            ),
            **metadata,
        }

        self.audit_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        async with self._audit_lock:
            with self.audit_path.open(
                "a",
                encoding="utf-8",
            ) as audit_file:
                audit_file.write(
                    json.dumps(event)
                    + "\n"
                )

    async def _execute_provider(
        self,
        request: dict,
    ) -> dict:
        """
        Execute one unique provider request with a timeout and
        concurrency limit.
        """

        started_at = perf_counter()

        async with self._semaphore:
            try:
                provider_result = await asyncio.wait_for(
                    self.provider(request),
                    timeout=self.timeout_seconds,
                )

                result = {
                    **provider_result,
                    "status": "success",
                }

            except asyncio.TimeoutError:
                result = {
                    "status": "timeout",
                    "answer": (
                        "The provider did not respond within "
                        "the configured time limit."
                    ),
                    "decision": "refuse",
                    "requires_human_approval": False,
                    "citations": [],
                    "rationale": (
                        "No Finance answer is produced after "
                        "a provider timeout."
                    ),
                }

            except Exception as error:
                result = {
                    "status": "provider_error",
                    "answer": (
                        "The provider request could not be completed."
                    ),
                    "decision": "refuse",
                    "requires_human_approval": False,
                    "citations": [],
                    "rationale": type(error).__name__,
                }

        elapsed_ms = round(
            (
                perf_counter()
                - started_at
            )
            * 1000,
            3,
        )

        result["latency_ms"] = elapsed_ms

        await self._write_audit(
            event_type="provider_request_completed",
            request=request,
            status=result["status"],
            decision=result["decision"],
            citations=result["citations"],
            requires_human_approval=result[
                "requires_human_approval"
            ],
            latency_ms=elapsed_ms,
        )

        return result

    async def _run_and_cache(
        self,
        request: dict,
    ) -> dict:
        """
        Run one unique request and cache only a successful result.
        """

        idempotency_key = request[
            "idempotency_key"
        ]

        try:
            result = await self._execute_provider(
                request
            )

            if result["status"] == "success":
                async with self._state_lock:
                    self._completed_results[
                        idempotency_key
                    ] = deepcopy(result)

            return result

        finally:
            async with self._state_lock:
                self._inflight_tasks.pop(
                    idempotency_key,
                    None,
                )

    async def process(
        self,
        request: dict,
    ) -> dict:
        """
        Process one request with idempotency protection.
        """

        idempotency_key = request.get(
            "idempotency_key"
        )

        if not idempotency_key:
            raise ValueError(
                "Every request requires an idempotency_key."
            )

        audit_event = None

        async with self._state_lock:
            if (
                idempotency_key
                in self._completed_results
            ):
                cached_result = deepcopy(
                    self._completed_results[
                        idempotency_key
                    ]
                )

                audit_event = (
                    "idempotency_cache_hit"
                )

                task = None
                reused = True

            else:
                task = self._inflight_tasks.get(
                    idempotency_key
                )

                if task is None:
                    task = asyncio.create_task(
                        self._run_and_cache(
                            request
                        )
                    )

                    self._inflight_tasks[
                        idempotency_key
                    ] = task

                    audit_event = (
                        "idempotency_operation_started"
                    )

                    reused = False

                else:
                    audit_event = (
                        "idempotency_inflight_joined"
                    )

                    reused = True

        await self._write_audit(
            event_type=audit_event,
            request=request,
        )

        if task is None:
            result = cached_result
        else:
            result = await task

        return {
            "request_id": request[
                "request_id"
            ],
            "idempotency_reused": reused,
            "result": deepcopy(result),
        }

    async def process_batch(
        self,
        requests: list[dict],
    ) -> list[dict]:
        """
        Process several requests concurrently while preserving
        their original list order.
        """

        return await asyncio.gather(
            *(
                self.process(request)
                for request in requests
            )
        )
