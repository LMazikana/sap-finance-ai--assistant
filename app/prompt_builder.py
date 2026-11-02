# DAY 7 — ACTIVITY 3: BUILD A VERSIONED PROMPT PACKET
#
# Purpose:
# Load the approved prompt template and safely insert:
# - The user's role
# - The user's question
# - Retrieved policy evidence
#
# This packet can later be sent to SAP Generative AI Hub
# or a Databricks model-serving endpoint.

import json
from pathlib import Path
from string import Template


# These fields must exist in every approved prompt template.
REQUIRED_TEMPLATE_FIELDS = {
    "prompt_id",
    "version",
    "description",
    "model_parameters",
    "system_prompt",
    "user_prompt_template",
}


def load_prompt_template(
    prompt_file: str = "prompts/finance_assistant_v1.json",
) -> dict:
    """
    Load and validate a versioned prompt template.
    """

    prompt_path = Path(prompt_file)

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt template was not found: {prompt_path}"
        )

    template_data = json.loads(
        prompt_path.read_text(encoding="utf-8")
    )

    # Identify missing required template fields.
    missing_fields = (
        REQUIRED_TEMPLATE_FIELDS - template_data.keys()
    )

    if missing_fields:
        raise ValueError(
            f"Prompt template is missing fields: "
            f"{sorted(missing_fields)}"
        )

    return template_data


def format_policy_context(
    retrieved_policies: list[dict],
) -> str:
    """
    Convert retrieved policies into a clearly bounded context.
    """

    if not retrieved_policies:
        return "NO_APPROVED_EVIDENCE"

    context_blocks = []

    for policy in retrieved_policies:
        context_blocks.append(
            "\n".join(
                [
                    f"POLICY_ID: {policy['policy_id']}",
                    f"TITLE: {policy['title']}",
                    f"POLICY_TEXT: {policy['text']}",
                    f"SOURCE: {policy['citation']}",
                ]
            )
        )

    # Separate each policy using a clear boundary.
    return "\n\n---\n\n".join(context_blocks)


def build_prompt_packet(
    question: str,
    user_role: str,
    retrieved_policies: list[dict],
    prompt_file: str = "prompts/finance_assistant_v1.json",
) -> dict:
    """
    Build model-ready system and user messages.

    The result is provider-independent and does not call an LLM.
    """

    # Load the approved, versioned prompt template.
    prompt_template = load_prompt_template(prompt_file)

    # Format retrieved evidence into a controlled context block.
    formatted_context = format_policy_context(
        retrieved_policies
    )

    # Insert variables using Python's standard Template class.
    user_message = Template(
        prompt_template["user_prompt_template"]
    ).substitute(
        user_role=user_role,
        question=question,
        context=formatted_context,
    )

    # Return messages plus traceable prompt metadata.
    return {
        "metadata": {
            "prompt_id": prompt_template["prompt_id"],
            "prompt_version": prompt_template["version"],
            "model_parameters": prompt_template[
                "model_parameters"
            ],
            "evidence_policy_ids": [
                policy["policy_id"]
                for policy in retrieved_policies
            ],
        },
        "messages": [
            {
                "role": "system",
                "content": prompt_template["system_prompt"],
            },
            {
                "role": "user",
                "content": user_message,
            },
        ],
    }
