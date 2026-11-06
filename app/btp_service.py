"""Deployment API for the governed SAP Finance assistant."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
import hashlib
import json
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


SERVICE_NAME = "governed-sap-finance-assistant"
SERVICE_VERSION = "0.24.0"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DECISION_PATH = (
    PROJECT_ROOT
    / "governance"
    / "day23_release_decision.json"
)

AUDIT_PATH = (
    PROJECT_ROOT
    / "audit"
    / "day24_api_audit.jsonl"
)


ROLE_POLICY_ACCESS = {
    "finance_analyst": {
        "FIN-JE-001",
        "FIN-CLOSE-001",
    },
    "finance_manager": {
        "FIN-JE-001",
        "FIN-CLOSE-001",
    },
    "controller": {
        "FIN-JE-001",
        "FIN-CLOSE-001",
    },
    "auditor": {
        "FIN-JE-001",
        "FIN-CLOSE-001",
    },
}


class FinanceQuestion(BaseModel):
    """Validated incoming Finance-assistant request."""

    user_id: str = Field(
        min_length=1,
        max_length=100,
    )

    role: str = Field(
        min_length=1,
        max_length=50,
    )

    business_unit: str = Field(
        min_length=1,
        max_length=50,
    )

    question: str = Field(
        min_length=3,
        max_length=2000,
    )


class FinanceDecision(BaseModel):
    """Core governed output contract."""

    answer: str

    decision: Literal[
        "answer",
        "refuse",
        "escalate",
    ]

    requires_human_approval: bool

    citations: list[str]

    rationale: str


class FinanceApiResponse(BaseModel):
    """API envelope containing the governed decision."""

    request_id: str
    result: FinanceDecision
    audit_event_id: str


def read_governance_decision() -> dict:
    """
    Read the latest release-gate decision.

    Missing governance evidence always produces a safe,
    unauthorized default.
    """

    if not DECISION_PATH.exists():
        return {
            "automated_technical_gate": "UNKNOWN",
            "human_approval_status": "UNKNOWN",
            "deployment_authorized": False,
        }

    return json.loads(
        DECISION_PATH.read_text(
            encoding="utf-8"
        )
    )


def append_audit_event(event: dict) -> None:
    """
    Append one JSON event to the audit log.
    """

    AUDIT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with AUDIT_PATH.open(
        "a",
        encoding="utf-8",
    ) as audit_file:
        audit_file.write(
            json.dumps(event)
            + "\n"
        )


def question_hash(question: str) -> str:
    """
    Create a traceable fingerprint without logging the raw question.
    """

    return hashlib.sha256(
        question.encode("utf-8")
    ).hexdigest()


def identify_policy(question: str):
    """
    Map the synthetic question to an approved policy.

    This is a deterministic deployment smoke-test implementation,
    not an LLM or production retrieval system.
    """

    normalized_question = question.lower()

    if (
        "journal" in normalized_question
        or "100,000" in normalized_question
        or "125,000" in normalized_question
    ):
        return {
            "policy_id": "FIN-JE-001",
            "answer": (
                "Journal entries above USD 100,000 require "
                "approval by a finance manager."
            ),
        }

    if (
        "period-end" in normalized_question
        or "adjustment" in normalized_question
        or "50,000" in normalized_question
    ):
        return {
            "policy_id": "FIN-CLOSE-001",
            "answer": (
                "Period-end adjustments above USD 50,000 "
                "require approval by a regional finance manager."
            ),
        }

    return None


app = FastAPI(
    title="Governed SAP Finance Assistant",
    version=SERVICE_VERSION,
)


@app.get("/health")
def health():
    """
    Confirm that the application process is operating.
    """

    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }


@app.get("/ready")
def ready():
    """
    Confirm that the automated technical gate passed.

    This does not claim that production deployment was authorized.
    """

    governance = read_governance_decision()

    if (
        governance.get(
            "automated_technical_gate"
        )
        != "PASS"
    ):
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "reason": (
                    "The automated technical gate has not passed."
                ),
            },
        )

    return {
        "status": "technical_ready",
        "technical_gate": "PASS",
        "human_approval_status": governance.get(
            "human_approval_status"
        ),
        "deployment_authorized": governance.get(
            "deployment_authorized",
            False,
        ),
    }


@app.get("/configuration")
def configuration():
    """
    Return only whether required SAP AI Core configuration exists.

    Credential values are never returned.
    """

    required_fields = [
        "AICORE_CLIENT_ID",
        "AICORE_CLIENT_SECRET",
        "AICORE_AUTH_URL",
        "AICORE_BASE_URL",
        "AICORE_RESOURCE_GROUP",
    ]

    field_status = {
        field_name: bool(
            os.getenv(field_name)
        )
        for field_name in required_fields
    }

    return {
        "sap_ai_core_configuration_complete": all(
            field_status.values()
        ),
        "credential_fields_present": field_status,
        "credential_values_exposed": False,
    }


@app.post(
    "/ask",
    response_model=FinanceApiResponse,
)
def ask_finance_assistant(
    request: FinanceQuestion,
):
    """
    Process a governed synthetic Finance request.
    """

    request_id = uuid4().hex
    audit_event_id = uuid4().hex

    governance = read_governance_decision()

    app_environment = os.getenv(
        "APP_ENV",
        "development",
    ).lower()

    # Production requests remain blocked until the governance
    # record explicitly authorizes deployment.
    if (
        app_environment == "production"
        and not governance.get(
            "deployment_authorized",
            False,
        )
    ):
        append_audit_event(
            {
                "audit_event_id": audit_event_id,
                "request_id": request_id,
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "event": "production_request_blocked",
                "question_sha256": question_hash(
                    request.question
                ),
                "role": request.role,
                "business_unit": request.business_unit,
            }
        )

        raise HTTPException(
            status_code=503,
            detail={
                "decision": "blocked",
                "reason": (
                    "Production deployment has not received "
                    "human authorization."
                ),
            },
        )

    normalized_role = request.role.lower()

    if normalized_role not in ROLE_POLICY_ACCESS:
        append_audit_event(
            {
                "audit_event_id": audit_event_id,
                "request_id": request_id,
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
                "event": "role_access_denied",
                "question_sha256": question_hash(
                    request.question
                ),
                "role": request.role,
                "business_unit": request.business_unit,
            }
        )

        raise HTTPException(
            status_code=403,
            detail={
                "decision": "refuse",
                "reason": "The role is not authorized.",
            },
        )

    policy = identify_policy(
        request.question
    )

    action_words = [
        "post",
        "approve",
        "reverse",
        "modify",
        "execute",
    ]

    normalized_question = (
        request.question.lower()
    )

    action_requested = any(
        action_word in normalized_question
        for action_word in action_words
    )

    permitted_policies = ROLE_POLICY_ACCESS[
        normalized_role
    ]

    if (
        policy is not None
        and policy["policy_id"]
        not in permitted_policies
    ):
        policy = None

    if action_requested:
        result = {
            "answer": (
                "I cannot execute the requested financial "
                "transaction. A human approver must review it."
            ),
            "decision": "escalate",
            "requires_human_approval": True,
            "citations": (
                [policy["policy_id"]]
                if policy is not None
                else []
            ),
            "rationale": (
                "Financial execution is outside the assistant's "
                "authority."
            ),
        }

    elif policy is not None:
        result = {
            "answer": policy["answer"],
            "decision": "answer",
            "requires_human_approval": False,
            "citations": [
                policy["policy_id"]
            ],
            "rationale": (
                "The answer is supported by an authorized "
                "synthetic Finance policy."
            ),
        }

    else:
        result = {
            "answer": (
                "I cannot answer because no authorized policy "
                "supports the request."
            ),
            "decision": "refuse",
            "requires_human_approval": False,
            "citations": [],
            "rationale": (
                "No authorized context was available."
            ),
        }

    append_audit_event(
        {
            "audit_event_id": audit_event_id,
            "request_id": request_id,
            "timestamp_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "event": "finance_request_completed",
            "question_sha256": question_hash(
                request.question
            ),
            "role": request.role,
            "business_unit": request.business_unit,
            "decision": result["decision"],
            "citations": result["citations"],
            "requires_human_approval": result[
                "requires_human_approval"
            ],
        }
    )

    return {
        "request_id": request_id,
        "result": result,
        "audit_event_id": audit_event_id,
    }
