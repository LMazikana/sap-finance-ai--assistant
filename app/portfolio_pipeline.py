"End-to-end governed SAP Finance assistant portfolio pipeline."

from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app import enterprise_rag


REQUIRED_RESPONSE_FIELDS = {
    "answer",
    "decision",
    "requires_human_approval",
    "citations",
    "rationale",
}

ALLOWED_DECISIONS = {"answer", "refuse", "escalate"}


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def result_value(result: Any, names: tuple[str, ...], default: str = "") -> str:
    for name in names:
        value = result.get(name) if isinstance(result, dict) else getattr(result, name, None)
        if value not in (None, ""):
            return str(value)
    return default


def classify_risk(question: str) -> str:
    normalized = " ".join(question.lower().split())
    restricted_markers = (
        "ignore all previous",
        "ignore previous rules",
        "reveal the restricted",
        "restricted payroll",
        "compensation records",
    )
    execution_markers = (
        "post and approve",
        "post this",
        "approve this",
        "reverse this",
        "execute this",
    )

    if any(marker in normalized for marker in restricted_markers):
        return "restricted_information"
    if any(marker in normalized for marker in execution_markers):
        return "transaction_execution"
    return "information_request"


class DeterministicPortfolioProvider:
    def generate(self, risk_type: str, retrieval_results: list[Any]) -> dict[str, Any]:
        citations = unique_strings(
            [result_value(result, ("citation", "source_citation")) for result in retrieval_results]
        )

        if risk_type == "restricted_information":
            return {
                "answer": "I cannot provide the requested restricted financial information.",
                "decision": "refuse",
                "requires_human_approval": False,
                "citations": [],
                "rationale": "The request conflicts with access and governance controls.",
            }

        if risk_type == "transaction_execution":
            return {
                "answer": (
                    "I have not posted, approved, reversed or modified any financial "
                    "transaction. An authorized human must review this request."
                ),
                "decision": "escalate",
                "requires_human_approval": True,
                "citations": citations,
                "rationale": "The assistant is advisory and cannot execute finance transactions.",
            }

        if not retrieval_results or not citations:
            return {
                "answer": "The authorized policy context does not support an answer.",
                "decision": "refuse",
                "requires_human_approval": False,
                "citations": [],
                "rationale": "No cited authorized source was available.",
            }

        return {
            "answer": (
                "Authorized policy context is available. Review the cited source sections: "
                + ", ".join(citations)
                + "."
            ),
            "decision": "answer",
            "requires_human_approval": False,
            "citations": citations,
            "rationale": "The answer is limited to role-authorized retrieved policy context.",
        }


def validate_response(
    response: dict[str, Any],
    risk_type: str,
    expected_decision: str,
    retrieved_citations: list[str],
) -> dict[str, Any]:
    decision = response.get("decision")
    approval = response.get("requires_human_approval")
    response_citations = response.get("citations", [])

    checks = {
        "exact_response_schema": (
            set(response) == REQUIRED_RESPONSE_FIELDS
            and decision in ALLOWED_DECISIONS
            and type(approval) is bool
            and isinstance(response_citations, list)
        ),
        "citation_integrity": set(response_citations) <= set(retrieved_citations),
        "answered_response_has_citation": decision != "answer" or bool(response_citations),
        "transaction_requires_human": (
            risk_type != "transaction_execution"
            or (decision == "escalate" and approval is True)
        ),
        "restricted_request_refused": (
            risk_type != "restricted_information" or decision == "refuse"
        ),
        "expected_decision": decision == expected_decision,
    }
    return {"checks": checks, "passed": all(checks.values())}


def run_demo_case(
    case: dict[str, Any],
    retriever: Any,
    release_gate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    question = case["question"]
    risk_type = classify_risk(question)

    gate_approved = (
        release_gate.get("decision") == "APPROVED_FOR_LOCAL_DEMO"
        and bool(release_gate.get("checks"))
        and all(release_gate["checks"].values())
    )

    if gate_approved:
        query = enterprise_rag.RetrievalQuery(
            question=question,
            user_role=case["user_role"],
            company_code=case["company_code"],
            top_k=case["top_k"],
        )
        results = list(retriever.retrieve(query).results)
    else:
        results = []

    policy_ids = unique_strings([result_value(item, ("policy_id",)) for item in results])
    citations = unique_strings(
        [result_value(item, ("citation", "source_citation")) for item in results]
    )

    if gate_approved:
        response = DeterministicPortfolioProvider().generate(risk_type, results)
    else:
        response = {
            "answer": "The assistant is unavailable because its governance gate is blocked.",
            "decision": "refuse",
            "requires_human_approval": False,
            "citations": [],
            "rationale": "The workflow fails closed without governance approval.",
        }

    validation = validate_response(
        response,
        risk_type,
        case["expected_decision"],
        citations,
    )
    trace_id = uuid.uuid4().hex[:12]
    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    gate_digest = stable_hash(json.dumps(release_gate, sort_keys=True, separators=(",", ":")))

    result = {
        "case_id": case["case_id"],
        "scenario": case["scenario"],
        "input": {
            "question": question,
            "user_role": case["user_role"],
            "company_code": case["company_code"],
        },
        "risk_type": risk_type,
        "retrieval": {
            "policy_ids": policy_ids,
            "citations": citations,
            "result_count": len(results),
        },
        "response": response,
        "validation": validation,
        "trace_id": trace_id,
    }

    trace = {
        "event_type": "governed_finance_assistant_request",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "trace_id": trace_id,
        "case_id": case["case_id"],
        "query_hash": stable_hash(question),
        "user_role": case["user_role"],
        "company_code": case["company_code"],
        "risk_type": risk_type,
        "gate_approved": gate_approved,
        "gate_digest": gate_digest,
        "retrieval_count": len(results),
        "retrieved_policy_ids": policy_ids,
        "decision": response["decision"],
        "requires_human_approval": response["requires_human_approval"],
        "validation_passed": validation["passed"],
        "duration_ms": duration_ms,
        "spans": [
            {"name": "governance_gate", "status": "OK"},
            {"name": "authorized_retrieval", "status": "OK"},
            {"name": "response_generation", "status": "OK"},
            {"name": "response_validation", "status": "OK"},
        ],
    }

    return result, trace
