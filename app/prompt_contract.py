"""Prompt rendering and output validation for the finance assistant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ALLOWED_USER_ROLES = {
    "finance_analyst",
    "finance_manager",
    "internal_auditor",
}

ALLOWED_DECISIONS = {
    "answer",
    "refuse",
    "escalate",
}

REQUIRED_OUTPUT_KEYS = {
    "answer",
    "decision",
    "requires_human_approval",
    "citations",
    "rationale",
}


def load_prompt_template(template_path: Path) -> dict[str, Any]:
    """Load a prompt template and verify its required structure."""

    template = json.loads(
        template_path.read_text(encoding="utf-8")
    )

    required_template_keys = {
        "name",
        "version",
        "scenario",
        "spec",
    }

    missing_keys = required_template_keys - set(template)

    if missing_keys:
        raise ValueError(
            f"Prompt template is missing fields: {sorted(missing_keys)}"
        )

    messages = template["spec"].get("template", [])
    roles = [message.get("role") for message in messages]

    if roles != ["system", "user"]:
        raise ValueError(
            "Prompt template must contain system and user roles in that order."
        )

    return template


def encode_untrusted_input(value: Any) -> str:
    """
    Convert an untrusted value into JSON for prompt insertion.

    Angle brackets are escaped so input cannot visually create new XML-like
    sections such as </user_question_json><system>.
    """

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )

    return (
        encoded
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_prompt(
    template: dict[str, Any],
    *,
    user_role: str,
    question: str,
    approved_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Render system and user messages without changing the system instructions.

    Only approved application roles may generate a model request.
    """

    if user_role not in ALLOWED_USER_ROLES:
        raise PermissionError(
            f"Role is not permitted: {user_role}"
        )

    if not isinstance(question, str) or not question.strip():
        raise ValueError("A non-empty question is required.")

    if not isinstance(approved_context, list):
        raise TypeError("approved_context must be a list.")

    template_messages = template["spec"]["template"]

    system_message = template_messages[0]["content"]
    user_message = template_messages[1]["content"]

    rendered_user_message = (
        user_message
        .replace(
            "{{?user_role}}",
            encode_untrusted_input(user_role),
        )
        .replace(
            "{{?question}}",
            encode_untrusted_input(question),
        )
        .replace(
            "{{?context_json}}",
            encode_untrusted_input(approved_context),
        )
    )

    additional_fields = template["spec"]["additional_fields"]

    return {
        "messages": [
            {
                "role": "system",
                "content": system_message,
            },
            {
                "role": "user",
                "content": rendered_user_message,
            },
        ],
        "response_format": additional_fields["response_format"],
        "model_parameters": additional_fields["modelParams"],
        "metadata": {
            "prompt_template_id": template["name"],
            "prompt_template_version": template["version"],
            "prompt_scenario": template["scenario"],
        },
    }


def validate_model_output(
    model_output: str | dict[str, Any],
    approved_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Validate both the JSON structure and finance-governance rules.

    This validation must run even when the model provider claims to enforce
    the JSON schema.
    """

    errors: list[str] = []

    if isinstance(model_output, str):
        try:
            payload = json.loads(model_output)
        except json.JSONDecodeError as error:
            return {
                "valid": False,
                "errors": [f"Invalid JSON: {error.msg}"],
                "payload": None,
            }
    elif isinstance(model_output, dict):
        payload = model_output
    else:
        return {
            "valid": False,
            "errors": ["Model output must be a JSON string or dictionary."],
            "payload": None,
        }

    if set(payload) != REQUIRED_OUTPUT_KEYS:
        missing = REQUIRED_OUTPUT_KEYS - set(payload)
        extra = set(payload) - REQUIRED_OUTPUT_KEYS

        if missing:
            errors.append(
                f"Missing output fields: {sorted(missing)}"
            )

        if extra:
            errors.append(
                f"Unexpected output fields: {sorted(extra)}"
            )

    answer = payload.get("answer")
    decision = payload.get("decision")
    approval_required = payload.get("requires_human_approval")
    citations = payload.get("citations")
    rationale = payload.get("rationale")

    if not isinstance(answer, str) or not answer.strip():
        errors.append("answer must be a non-empty string.")

    if decision not in ALLOWED_DECISIONS:
        errors.append(
            f"decision must be one of {sorted(ALLOWED_DECISIONS)}."
        )

    if not isinstance(approval_required, bool):
        errors.append("requires_human_approval must be boolean.")

    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("rationale must be a non-empty string.")

    approved_policy_ids = {
        str(item["policy_id"])
        for item in approved_context
        if item.get("policy_id")
    }

    if not isinstance(citations, list) or not all(
        isinstance(citation, str)
        for citation in citations
    ):
        errors.append("citations must be a list of strings.")
    else:
        unknown_citations = set(citations) - approved_policy_ids

        if unknown_citations:
            errors.append(
                "Unknown citations: "
                f"{sorted(unknown_citations)}"
            )

        if decision == "answer" and not citations:
            errors.append(
                "An answered policy question requires at least one citation."
            )

    if decision == "escalate" and approval_required is not True:
        errors.append(
            "An escalated decision requires human approval."
        )

    return {
        "valid": not errors,
        "errors": errors,
        "payload": payload,
    }
