from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re


PATTERNS = [
    ("IBAN", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")),
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("BANK_ACCOUNT", re.compile(r"(?<![A-Z0-9])\d{8,17}(?![A-Z0-9])")),
]


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def zero_masking_summary() -> dict:
    return {entity_name: 0 for entity_name, _ in PATTERNS}


def anonymize_text(value: str) -> tuple[str, dict]:
    masked_value = value
    counts = zero_masking_summary()

    for entity_name, entity_pattern in PATTERNS:
        def replace_match(match, entity=entity_name):
            counts[entity] += 1
            return f"<{entity}_{counts[entity]}>"

        masked_value = entity_pattern.sub(replace_match, masked_value)

    return masked_value, counts


def merge_counts(*count_sets: dict) -> dict:
    merged = zero_masking_summary()
    for count_set in count_sets:
        for key, value in count_set.items():
            merged[key] += value
    return merged


def find_prompt_injection(question: str, patterns: list[str]):
    normalized_question = question.casefold()
    return next(
        (pattern for pattern in patterns if pattern.casefold() in normalized_question),
        None,
    )


def blocked_build(case: dict, reason: str, matched_pattern=None) -> dict:
    return {
        "status": "blocked",
        "block_reason": reason,
        "matched_pattern": matched_pattern,
        "question_sha256": sha256_text(case["question"]),
        "approved_policy_ids": [],
        "masking_summary": zero_masking_summary(),
        "provider_request": None,
    }


def build_orchestration_request(case: dict, contract: dict) -> dict:
    role = case["user_role"]
    business_unit = case["business_unit"]
    question = case["question"]

    if role not in contract["authorization"]["allowed_roles"]:
        return blocked_build(case, "unauthorized_role")

    matched_pattern = find_prompt_injection(
        question,
        contract["modules"]["filtering"]["input"]["prompt_shield_patterns"],
    )
    if matched_pattern:
        return blocked_build(case, "prompt_injection", matched_pattern)

    authorized_context = []
    rejected_context_count = 0

    for policy in case.get("approved_context", []):
        role_allowed = role in policy.get("allowed_roles", [])
        allowed_units = policy.get("business_units", [])
        unit_allowed = (
            "GLOBAL" in allowed_units
            or business_unit in allowed_units
        )

        if role_allowed and unit_allowed:
            authorized_context.append(policy)
        else:
            rejected_context_count += 1

    masked_question, question_counts = anonymize_text(question)
    masked_context = []
    all_masking_counts = [question_counts]

    for policy in authorized_context:
        masked_text, context_counts = anonymize_text(policy["text"])
        all_masking_counts.append(context_counts)
        masked_context.append({
            "policy_id": policy["policy_id"],
            "text": masked_text,
        })

    masking_summary = merge_counts(*all_masking_counts)
    approved_policy_ids = [policy["policy_id"] for policy in masked_context]

    provider_request = {
        "target_service": contract["target_service"],
        "contract_id": contract["contract_id"],
        "contract_version": contract["version"],
        "module_configurations": {
            "prompt_templating": {
                "messages": contract["modules"]["prompt_templating"]["messages"],
                "placeholder_values": {
                    "user_role": role,
                    "business_unit": business_unit,
                    "question": masked_question,
                    "approved_context": masked_context,
                },
            },
            "model": contract["modules"]["model"],
            "masking": contract["modules"]["masking"],
            "filtering": contract["modules"]["filtering"],
            "grounding": {
                **contract["modules"]["grounding"],
                "approved_policy_ids": approved_policy_ids,
            },
        },
        "metadata": {
            "case_id": case["case_id"],
            "question_sha256": sha256_text(question),
            "rejected_context_count": rejected_context_count,
        },
    }

    return {
        "status": "request_prepared",
        "block_reason": None,
        "matched_pattern": None,
        "question_sha256": sha256_text(question),
        "approved_policy_ids": approved_policy_ids,
        "masking_summary": masking_summary,
        "provider_request": provider_request,
    }


def simulate_finance_response(case: dict, build_result: dict) -> dict:
    if build_result["status"] == "blocked":
        return {
            "answer": "The request was blocked before model execution.",
            "decision": "refuse",
            "requires_human_approval": False,
            "citations": [],
            "rationale": build_result["block_reason"],
        }

    context = build_result["provider_request"]["module_configurations"]["prompt_templating"]["placeholder_values"]["approved_context"]
    normalized_question = case["question"].casefold()
    action_requested = any(
        action_word in normalized_question
        for action_word in ["post", "approve", "reverse", "execute", "modify"]
    )

    if action_requested:
        citations = [context[0]["policy_id"]] if context else []
        return {
            "answer": "I cannot execute this Finance action. A human approver must review it.",
            "decision": "escalate",
            "requires_human_approval": True,
            "citations": citations,
            "rationale": "Financial execution is outside the assistant's authority.",
        }

    if not context:
        return {
            "answer": "No approved policy context supports an answer.",
            "decision": "refuse",
            "requires_human_approval": False,
            "citations": [],
            "rationale": "The authorized grounding context is empty.",
        }

    return {
        "answer": context[0]["text"],
        "decision": "answer",
        "requires_human_approval": False,
        "citations": [context[0]["policy_id"]],
        "rationale": "The response is supported by authorized policy context.",
    }


def validate_response(response: dict, build_result: dict, contract: dict) -> dict:
    output_contract = contract["output_contract"]
    required_fields = set(output_contract["required_fields"])
    actual_fields = set(response)
    allowed_decisions = set(output_contract["allowed_decisions"])
    approved_ids = set(build_result["approved_policy_ids"])
    citations = response.get("citations", [])

    checks = {
        "exact_fields": actual_fields == required_fields,
        "valid_decision": response.get("decision") in allowed_decisions,
        "citations_are_a_list": isinstance(citations, list),
        "citations_are_authorized": isinstance(citations, list) and set(citations).issubset(approved_ids),
        "answer_has_citation": response.get("decision") != "answer" or bool(citations),
        "refusal_has_no_citation": response.get("decision") != "refuse" or citations == [],
        "approval_matches_escalation": (
            response.get("requires_human_approval")
            is (response.get("decision") == "escalate")
        ),
    }

    return {"valid": all(checks.values()), "checks": checks}


def build_audit_event(case: dict, build_result: dict, response: dict) -> dict:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event_type": (
            "orchestration_request_blocked"
            if build_result["status"] == "blocked"
            else "orchestration_request_prepared"
        ),
        "case_id": case["case_id"],
        "user_role": case["user_role"],
        "business_unit": case["business_unit"],
        "question_sha256": build_result["question_sha256"],
        "status": build_result["status"],
        "block_reason": build_result["block_reason"],
        "approved_policy_ids": build_result["approved_policy_ids"],
        "masking_summary": build_result["masking_summary"],
        "decision": response["decision"],
        "requires_human_approval": response["requires_human_approval"],
        "external_provider_called": False,
    }
