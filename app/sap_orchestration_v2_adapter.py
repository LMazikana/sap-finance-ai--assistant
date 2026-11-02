"""Credential-free SAP Generative AI Hub Orchestration V2 adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any


ALLOWED_DECISIONS = {"answer", "refuse", "escalate"}

REQUIRED_RESPONSE_FIELDS = {
    "answer",
    "decision",
    "requires_human_approval",
    "citations",
    "rationale",
}

FORBIDDEN_CREDENTIAL_KEYS = {
    "authorization",
    "access_token",
    "client_secret",
    "client_id",
    "github_token",
    "password",
    "api_key",
}


@dataclass(frozen=True)
class SapOrchestrationSettings:
    """Non-secret settings used to construct an orchestration request."""

    model_name: str
    temperature: float = 0.1
    max_completion_tokens: int = 500

    def __post_init__(self) -> None:
        if not self.model_name.strip():
            raise ValueError("model_name must not be empty.")

        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0.")

        if self.max_completion_tokens <= 0:
            raise ValueError(
                "max_completion_tokens must be greater than zero."
            )


@dataclass(frozen=True)
class GovernedFinanceResult:
    """Validated structured response from the Finance assistant."""

    answer: str
    decision: str
    requires_human_approval: bool
    citations: tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""

        result = asdict(self)
        result["citations"] = list(self.citations)
        return result


def find_forbidden_credential_keys(value: Any) -> list[str]:
    """Return payload locations containing credential-related keys."""

    matches: list[str] = []

    def walk(item: Any, location: str) -> None:
        if isinstance(item, Mapping):
            for key, child_value in item.items():
                normalized_key = str(key).strip().lower()
                child_location = f"{location}.{key}"

                if normalized_key in FORBIDDEN_CREDENTIAL_KEYS:
                    matches.append(child_location)

                walk(child_value, child_location)

        elif isinstance(item, (list, tuple)):
            for index, child_value in enumerate(item):
                walk(child_value, f"{location}[{index}]")

    walk(value, "payload")
    return matches


class SapOrchestrationV2Adapter:
    """Build and validate SAP Orchestration V2 Finance requests."""

    def __init__(self, settings: SapOrchestrationSettings) -> None:
        self.settings = settings

    @property
    def provider_name(self) -> str:
        return "sap-generative-ai-hub-orchestration-v2"

    def build_payload(
        self,
        *,
        system_prompt: str,
        question: str,
        user_role: str,
        approved_context: Any,
    ) -> dict[str, Any]:
        """Build an inline Orchestration V2 completion payload."""

        if not system_prompt.strip():
            raise ValueError("system_prompt must not be empty.")

        if not question.strip():
            raise ValueError("question must not be empty.")

        if not user_role.strip():
            raise ValueError("user_role must not be empty.")

        if isinstance(approved_context, str):
            context_text = approved_context.strip()
        else:
            context_text = json.dumps(
                approved_context,
                ensure_ascii=False,
                sort_keys=True,
            )

        if not context_text:
            raise ValueError("approved_context must not be empty.")

        # Placeholder syntax keeps runtime data separate from the
        # higher-priority system instructions.
        user_template = """USER_ROLE: {{?user_role}}

USER_QUESTION:
<question>
{{?question}}
</question>

APPROVED_POLICY_CONTEXT:
<context>
{{?context}}
</context>

Return one valid JSON object only.
"""

        payload = {
            "config": {
                "modules": {
                    "prompt_templating": {
                        "prompt": {
                            "template": [
                                {
                                    "role": "system",
                                    "content": system_prompt,
                                },
                                {
                                    "role": "user",
                                    "content": user_template,
                                },
                            ],
                            "response_format": {
                                "type": "json_object",
                            },
                        },
                        "model": {
                            "name": self.settings.model_name,
                            "params": {
                                "temperature": self.settings.temperature,
                                "max_completion_tokens": (
                                    self.settings.max_completion_tokens
                                ),
                            },
                        },
                    }
                }
            },
            "placeholder_values": {
                "user_role": user_role,
                "question": question,
                "context": context_text,
            },
        }

        forbidden_keys = find_forbidden_credential_keys(payload)

        if forbidden_keys:
            raise ValueError(
                f"Credential fields found in payload: {forbidden_keys}"
            )

        return payload

    def parse_response(
        self,
        response: Mapping[str, Any],
    ) -> GovernedFinanceResult:
        """Validate an SAP Orchestration V2 structured response."""

        try:
            content = response["final_result"]["choices"][0]["message"][
                "content"
            ]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError(
                "Response does not have the expected SAP V2 structure."
            ) from error

        if isinstance(content, str):
            try:
                result_data = json.loads(content)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "The model response is not valid JSON."
                ) from error

        elif isinstance(content, Mapping):
            result_data = dict(content)

        else:
            raise ValueError(
                "The model response content must be JSON text or an object."
            )

        actual_fields = set(result_data)

        if actual_fields != REQUIRED_RESPONSE_FIELDS:
            missing = sorted(REQUIRED_RESPONSE_FIELDS - actual_fields)
            extra = sorted(actual_fields - REQUIRED_RESPONSE_FIELDS)

            raise ValueError(
                f"Invalid response fields. Missing: {missing}; extra: {extra}"
            )

        decision = result_data["decision"]

        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"Unsupported decision: {decision}")

        if type(result_data["requires_human_approval"]) is not bool:
            raise ValueError(
                "requires_human_approval must be a Boolean value."
            )

        citations = result_data["citations"]

        if not isinstance(citations, list) or not all(
            isinstance(citation, str) for citation in citations
        ):
            raise ValueError("citations must be a list of strings.")

        if (
            decision == "escalate"
            and not result_data["requires_human_approval"]
        ):
            raise ValueError(
                "An escalated request must require human approval."
            )

        return GovernedFinanceResult(
            answer=str(result_data["answer"]),
            decision=decision,
            requires_human_approval=(
                result_data["requires_human_approval"]
            ),
            citations=tuple(citations),
            rationale=str(result_data["rationale"]),
        )
