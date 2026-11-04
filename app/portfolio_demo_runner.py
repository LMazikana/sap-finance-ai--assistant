"""End-to-end portfolio demonstration runner."""

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import hashlib
import json
import os

from fastapi.testclient import TestClient

from app.btp_service import app


def canonical_json(payload: dict) -> str:
    """Create deterministic JSON for hashing."""

    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def calculate_hash(payload: dict) -> str:
    """Calculate a SHA-256 hash for one record."""

    return hashlib.sha256(
        canonical_json(payload).encode(
            "utf-8"
        )
    ).hexdigest()


def hash_question(question: str) -> str:
    """Fingerprint a question without storing its raw text."""

    return hashlib.sha256(
        question.encode("utf-8")
    ).hexdigest()


def verify_trace_chain(trace_path: Path) -> dict:
    """Recalculate every hash in a stored trace chain."""

    trace_lines = [
        line
        for line in trace_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    expected_previous_hash = "GENESIS"

    for line_number, trace_line in enumerate(
        trace_lines,
        start=1,
    ):
        record = json.loads(trace_line)

        stored_record_hash = record.pop(
            "record_hash"
        )

        previous_hash_is_valid = (
            record["previous_hash"]
            == expected_previous_hash
        )

        calculated_record_hash = (
            calculate_hash(record)
        )

        current_hash_is_valid = (
            stored_record_hash
            == calculated_record_hash
        )

        if not (
            previous_hash_is_valid
            and current_hash_is_valid
        ):
            return {
                "valid": False,
                "record_count": len(trace_lines),
                "failed_line": line_number,
            }

        expected_previous_hash = (
            stored_record_hash
        )

    return {
        "valid": True,
        "record_count": len(trace_lines),
        "failed_line": None,
        "final_hash": expected_previous_hash,
    }


def run_portfolio_demo(
    project_root: Path,
    scenarios_path: Path,
    results_path: Path,
    trace_path: Path,
) -> dict:
    """Run every synthetic portfolio scenario."""

    scenarios = json.loads(
        scenarios_path.read_text(
            encoding="utf-8"
        )
    )

    client = TestClient(app)

    original_app_environment = os.environ.get(
        "APP_ENV"
    )

    results = []
    traces = []
    previous_hash = "GENESIS"

    try:
        for scenario in scenarios:
            os.environ["APP_ENV"] = scenario[
                "app_environment"
            ]

            request_payload = scenario[
                "request"
            ]

            started_at = perf_counter()

            response = client.post(
                "/ask",
                json=request_payload,
            )

            elapsed_ms = round(
                (
                    perf_counter()
                    - started_at
                )
                * 1000,
                3,
            )

            response_body = response.json()

            if response.status_code == 200:
                result_payload = response_body[
                    "result"
                ]
            else:
                result_payload = response_body.get(
                    "detail",
                    {},
                )

            actual_decision = (
                result_payload.get(
                    "decision",
                    "unknown",
                )
            )

            actual_citations = (
                result_payload.get(
                    "citations",
                    [],
                )
            )

            actual_human_approval = (
                result_payload.get(
                    "requires_human_approval"
                )
            )

            expectations = scenario[
                "expected"
            ]

            checks = {
                "http_status": (
                    response.status_code
                    == expectations[
                        "http_status"
                    ]
                ),
                "decision": (
                    actual_decision
                    == expectations[
                        "decision"
                    ]
                ),
                "citations": (
                    actual_citations
                    == expectations[
                        "citations"
                    ]
                ),
                "human_approval": (
                    expectations[
                        "requires_human_approval"
                    ]
                    is None
                    or actual_human_approval
                    == expectations[
                        "requires_human_approval"
                    ]
                ),
            }

            scenario_passed = all(
                checks.values()
            )

            scenario_result = {
                "scenario_id": scenario[
                    "scenario_id"
                ],
                "name": scenario["name"],
                "passed": scenario_passed,
                "checks": checks,
                "actual": {
                    "http_status": (
                        response.status_code
                    ),
                    "decision": (
                        actual_decision
                    ),
                    "citations": (
                        actual_citations
                    ),
                    "requires_human_approval": (
                        actual_human_approval
                    ),
                },
                "latency_ms": elapsed_ms,
            }

            results.append(
                scenario_result
            )

            trace_record = {
                "trace_id": uuid4().hex,
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "scenario_id": scenario[
                    "scenario_id"
                ],
                "span_name": (
                    "governed_finance_request"
                ),
                "input_metadata": {
                    "question_sha256": (
                        hash_question(
                            request_payload[
                                "question"
                            ]
                        )
                    ),
                    "role": request_payload[
                        "role"
                    ],
                    "business_unit": (
                        request_payload[
                            "business_unit"
                        ]
                    ),
                    "app_environment": (
                        scenario[
                            "app_environment"
                        ]
                    ),
                },
                "output_metadata": {
                    "http_status": (
                        response.status_code
                    ),
                    "decision": (
                        actual_decision
                    ),
                    "citations": (
                        actual_citations
                    ),
                    "requires_human_approval": (
                        actual_human_approval
                    ),
                },
                "evaluation": {
                    "passed": scenario_passed,
                    "checks": checks,
                },
                "latency_ms": elapsed_ms,
                "previous_hash": previous_hash,
            }

            record_hash = calculate_hash(
                trace_record
            )

            trace_record[
                "record_hash"
            ] = record_hash

            previous_hash = record_hash

            traces.append(
                trace_record
            )

    finally:
        if original_app_environment is None:
            os.environ.pop(
                "APP_ENV",
                None,
            )
        else:
            os.environ[
                "APP_ENV"
            ] = original_app_environment

    trace_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    trace_path.write_text(
        "\n".join(
            json.dumps(
                trace_record,
                ensure_ascii=False,
            )
            for trace_record in traces
        )
        + "\n",
        encoding="utf-8",
    )

    trace_validation = verify_trace_chain(
        trace_path
    )

    passed_scenarios = sum(
        scenario_result["passed"]
        for scenario_result in results
    )

    report = {
        "demo_id": (
            "day25-governed-finance-portfolio-demo"
        ),
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "scenario_count": len(results),
        "passed_scenarios": passed_scenarios,
        "pass_rate": round(
            passed_scenarios / len(results),
            4,
        ),
        "trace_chain": trace_validation,
        "results": results,
    }

    results_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    return report
