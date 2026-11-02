"""HTTP service for the governed SAP Finance assistant."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from app.governance import (
    append_audit_event,
    build_audit_event,
    determine_expected_decision,
    validate_assistant_response,
)
from app.rag_pipeline import retrieve_chunks


# Basic service metadata.
SERVICE_NAME = "sap-finance-ai-assistant"
SERVICE_VERSION = "0.1.0"

# Find the repository root from this Python file's location.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Reference the citation-ready policy chunks.
POLICY_CHUNKS_FILE = PROJECT_ROOT.joinpath(
    "data",
    "finance_policy_chunks.json",
)

# Optional local audit location.
#
# Production will use standard output and centralized
# application logging instead of container-local storage.
LOCAL_AUDIT_FILE = PROJECT_ROOT.joinpath(
    "logs",
    "runtime_audit.jsonl",
)


def load_policy_chunks() -> list[dict[str, Any]]:
    """Load citation-ready policy chunks from JSON."""

    return json.loads(
        POLICY_CHUNKS_FILE.read_text(encoding="utf-8")
    )


# Load the approved synthetic evidence at application start.
POLICY_CHUNKS = load_policy_chunks()


def create_candidate_response(
    question: str,
    retrieved_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Create a deterministic response for deployment testing.

    A future production version will replace the deterministic
    answer generation with SAP Generative AI Hub orchestration.
    """

    decision = determine_expected_decision(
        question=question,
        retrieved_evidence=retrieved_evidence,
    )

    evidence_policy_ids = sorted(
        {
            evidence["policy_id"]
            for evidence in retrieved_evidence
        }
    )

    # Supported informational request.
    if decision == "answer":
        strongest_evidence = retrieved_evidence[0]

        return {
            "answer": (
                f"According to {strongest_evidence['title']}: "
                f"{strongest_evidence['text']}"
            ),
            "decision": "answer",
            "requires_human_approval": False,
            "citations": evidence_policy_ids,
            "rationale": (
                "The response is grounded in authorized "
                "retrieved policy evidence."
            ),
        }

    # Financial execution request.
    if decision == "escalate":
        return {
            "answer": (
                "I cannot execute or approve this financial "
                "transaction. The request requires human review."
            ),
            "decision": "escalate",
            "requires_human_approval": True,
            "citations": evidence_policy_ids,
            "rationale": (
                "Financial execution is restricted to an "
                "authorized human decision-maker."
            ),
        }

    # Unsupported, unauthorized or unsafe request.
    return {
        "answer": (
            "I cannot answer this request using approved "
            "and authorized policy evidence."
        ),
        "decision": "refuse",
        "requires_human_approval": False,
        "citations": [],
        "rationale": (
            "The request was unsafe, unsupported or lacked "
            "authorized evidence."
        ),
    }


def emit_audit_event(event: dict[str, Any]) -> None:
    """
    Emit a privacy-conscious audit event.

    Cloud Foundry captures standard output, which can be sent
    to an approved centralized logging service.
    """

    print(
        "AUDIT_EVENT " + json.dumps(event, sort_keys=True),
        flush=True,
    )

    # Local audit-file storage is disabled by default.
    #
    # It can be enabled explicitly for a local demonstration,
    # but should remain disabled in Cloud Foundry because
    # application-container storage is temporary.
    local_file_enabled = os.getenv(
        "ENABLE_LOCAL_AUDIT_FILE",
        "false",
    ).lower() == "true"

    if local_file_enabled:
        append_audit_event(
            event=event,
            audit_file=LOCAL_AUDIT_FILE,
        )


# Create the Flask application.
app = Flask(__name__)


@app.get("/health")
def health() -> tuple[Any, int]:
    """
    Return service-health information.

    SAP BTP Cloud Foundry can call this endpoint to determine
    whether the application is healthy.
    """

    return jsonify(
        {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "environment": os.getenv(
                "APP_ENV",
                "local",
            ),
            "model_mode": os.getenv(
                "MODEL_MODE",
                "deterministic-preview",
            ),
            "policy_chunks_loaded": len(POLICY_CHUNKS),
        }
    ), 200


@app.post("/v1/finance/ask")
def ask_finance_assistant() -> tuple[Any, int]:
    """
    Process a governed finance-assistant request.

    Required JSON fields:
    - question
    - user_role
    """

    request_body = request.get_json(silent=True) or {}

    question = str(
        request_body.get("question", "")
    ).strip()

    user_role = str(
        request_body.get("user_role", "")
    ).strip()

    # Reject incomplete requests before retrieval.
    if not question or not user_role:
        return jsonify(
            {
                "error": "invalid_request",
                "message": (
                    "question and user_role are required."
                ),
            }
        ), 400

    # Read retrieval depth from configuration.
    top_k = int(
        os.getenv("RETRIEVAL_TOP_K", "3")
    )

    # Apply role filtering while retrieving evidence.
    retrieved_evidence = retrieve_chunks(
        query=question,
        user_role=user_role,
        chunks=POLICY_CHUNKS,
        top_k=top_k,
    )

    # Create a deterministic preview response.
    candidate_response = create_candidate_response(
        question=question,
        retrieved_evidence=retrieved_evidence,
    )

    # Apply the Day 9 governance validator.
    validation = validate_assistant_response(
        question=question,
        response=candidate_response,
        retrieved_evidence=retrieved_evidence,
    )

    # Accept a caller-supplied request ID or generate one.
    request_id = (
        request.headers.get("X-Request-ID")
        or str(uuid.uuid4())
    )

    # Build an audit event without storing the raw question.
    audit_event = build_audit_event(
        event_id=request_id,
        user_role=user_role,
        question=question,
        response=candidate_response,
        validation=validation,
    )

    audit_event["service_version"] = SERVICE_VERSION

    emit_audit_event(audit_event)

    # Never return an answer that failed governance.
    if not validation["passed"]:
        return jsonify(
            {
                "request_id": request_id,
                "error": "governance_validation_failed",
                "violations": validation["violations"],
            }
        ), 500

    # HTTP 202 means the request was accepted for review.
    status_code = (
        202
        if candidate_response["decision"] == "escalate"
        else 200
    )

    return jsonify(
        {
            "request_id": request_id,
            "result": candidate_response,
            "governance": {
                "validated": True,
                "evidence_count": len(
                    retrieved_evidence
                ),
                "risk_flags": validation["risk_flags"],
            },
        }
    ), status_code


if __name__ == "__main__":
    # Cloud Foundry dynamically provides the PORT variable.
    #
    # Port 8080 is used only when running outside
    # Cloud Foundry.
    application_port = int(
        os.getenv("PORT", "8080")
    )

    app.run(
        host="0.0.0.0",
        port=application_port,
    )
