"""Governance controls for the SAP Finance AI assistant."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {
    "answer",
    "refuse",
    "escalate",
}


REQUIRED_RESPONSE_FIELDS = {
    "answer",
    "decision",
    "requires_human_approval",
    "citations",
    "rationale",
}


# These patterns provide a transparent local demonstration.
# A production application should also use managed input
# filtering and prompt-shield capabilities.
INJECTION_PATTERNS = [
    (
        "instruction_override",
        r"ignore\s+(?:all\s+)?"
        r"(?:previous|prior|system)\s+"
        r"(?:rules|instructions|prompts?)",
    ),
    (
        "system_prompt_extraction",
        r"\b(reveal|show|print|expose)\b.*"
        r"\b(system prompt|hidden instructions)\b",
    ),
    (
        "credential_extraction",
        r"\b(reveal|show|print|expose)\b.*"
        r"\b(secret|credential|token|password|api key)\b",
    ),
]


# These actions must never be performed automatically
# by the finance assistant.
FINANCIAL_ACTION_PATTERN = (
    r"\b(post|book|execute|approve|reverse|modify|"
    r"release|pay)\b.*"
    r"\b(journal entry|entry|invoice|payment|transaction)\b"
)


def detect_risk_flags(question: str) -> list[str]:
    """Return security and action risks found in a question."""

    risk_flags: list[str] = []

    for flag_name, pattern in INJECTION_PATTERNS:
        if re.search(
            pattern,
            question,
            flags=re.IGNORECASE,
        ):
            risk_flags.append(flag_name)

    if re.search(
        FINANCIAL_ACTION_PATTERN,
        question,
        flags=re.IGNORECASE,
    ):
        risk_flags.append(
            "financial_execution_request"
        )

    return sorted(set(risk_flags))


def determine_expected_decision(
    question: str,
    retrieved_evidence: list[dict[str, Any]],
) -> str:
    """Determine the decision required by governance policy."""

    risk_flags = detect_risk_flags(question)

    # Prompt manipulation takes priority over other processing.
    injection_flags = {
        "instruction_override",
        "system_prompt_extraction",
        "credential_extraction",
    }

    if injection_flags.intersection(risk_flags):
        return "refuse"

    # Execution requests require a human decision-maker.
    if "financial_execution_request" in risk_flags:
        return "escalate"

    # The assistant must not answer without approved evidence.
    if not retrieved_evidence:
        return "refuse"

    return "answer"


def validate_assistant_response(
    question: str,
    response: dict[str, Any],
    retrieved_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate structure, grounding and approval behavior."""

    violations: list[str] = []

    response_fields = set(response)
    missing_fields = (
        REQUIRED_RESPONSE_FIELDS - response_fields
    )
    unexpected_fields = (
        response_fields - REQUIRED_RESPONSE_FIELDS
    )

    if missing_fields:
        violations.append(
            "missing_fields:"
            + ",".join(sorted(missing_fields))
        )

    if unexpected_fields:
        violations.append(
            "unexpected_fields:"
            + ",".join(sorted(unexpected_fields))
        )

    decision = response.get("decision")
    approval_required = response.get(
        "requires_human_approval"
    )
    citations = response.get("citations", [])

    if decision not in ALLOWED_DECISIONS:
        violations.append("invalid_decision")

    if not isinstance(approval_required, bool):
        violations.append(
            "requires_human_approval_must_be_boolean"
        )

    if not isinstance(citations, list):
        violations.append("citations_must_be_a_list")
        citations = []

    evidence_policy_ids = sorted(
        {
            str(item["policy_id"])
            for item in retrieved_evidence
        }
    )

    unsupported_citations = sorted(
        {
            str(citation)
            for citation in citations
            if str(citation) not in evidence_policy_ids
        }
    )

    if unsupported_citations:
        violations.append(
            "unsupported_citations:"
            + ",".join(unsupported_citations)
        )

    expected_decision = determine_expected_decision(
        question=question,
        retrieved_evidence=retrieved_evidence,
    )

    if decision != expected_decision:
        violations.append(
            f"expected_decision:{expected_decision}"
        )

    if (
        expected_decision == "escalate"
        and approval_required is not True
    ):
        violations.append(
            "human_approval_required"
        )

    if decision == "answer" and not evidence_policy_ids:
        violations.append(
            "answer_without_evidence"
        )

    if decision == "answer" and not citations:
        violations.append(
            "grounded_answer_requires_citation"
        )

    if not str(response.get("answer", "")).strip():
        violations.append("answer_text_is_empty")

    if not str(response.get("rationale", "")).strip():
        violations.append("rationale_is_empty")

    return {
        "passed": not violations,
        "expected_decision": expected_decision,
        "risk_flags": detect_risk_flags(question),
        "evidence_policy_ids": evidence_policy_ids,
        "violations": violations,
    }


def hash_question(question: str) -> str:
    """Hash the question instead of storing its raw contents."""

    return hashlib.sha256(
        question.encode("utf-8")
    ).hexdigest()


def build_audit_event(
    event_id: str,
    user_role: str,
    question: str,
    response: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Create an audit event without raw prompt or answer text."""

    return {
        "event_id": event_id,
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "user_role": user_role,
        "question_sha256": hash_question(question),
        "evidence_policy_ids": validation[
            "evidence_policy_ids"
        ],
        "proposed_decision": response.get("decision"),
        "expected_decision": validation[
            "expected_decision"
        ],
        "requires_human_approval": response.get(
            "requires_human_approval"
        ),
        "validation_passed": validation["passed"],
        "risk_flags": validation["risk_flags"],
        "violations": validation["violations"],
        "human_review_status": (
            "pending"
            if validation["expected_decision"]
            == "escalate"
            else "not_required"
        ),
    }


def append_audit_event(
    event: dict[str, Any],
    audit_file: str | Path,
) -> bool:
    """Append an event unless its event ID already exists."""

    audit_path = Path(audit_file)
    audit_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing_event_ids: set[str] = set()

    if audit_path.exists():
        for line in audit_path.read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue

            existing_event = json.loads(line)
            existing_event_ids.add(
                existing_event["event_id"]
            )

    # Make repeated notebook execution idempotent.
    if event["event_id"] in existing_event_ids:
        return False

    with audit_path.open(
        mode="a",
        encoding="utf-8",
    ) as audit_stream:
        audit_stream.write(
            json.dumps(event, sort_keys=True)
            + "\n"
        )

    return True
