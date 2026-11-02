# Day 21 — Prompt Contract and Hardening

## Objective

Create a versioned prompt contract for the governed SAP Finance assistant.

## What I implemented

- Separate system and user roles.
- Explicit treatment of questions and retrieved documents as untrusted data.
- JSON encoding and angle-bracket escaping for dynamic input.
- A strict five-field response schema.
- Role-aware request rendering.
- Citation allow-list validation.
- Human-approval validation for escalated requests.
- Deterministic prompt-injection and output-contract tests.

## Results

- Tests passed: 9/9
- Prompt version: 2.0.0
- Prompt file: `prompts/finance_assistant_v2.json`
- Validation module: `app/prompt_contract.py`

## SAP Generative AI Hub alignment

The prompt is stored separately from application code, includes a stable
version, uses system and user roles, and can later be adapted to SAP Prompt
Registry and Orchestration Service.

## Databricks alignment

The prompt bundle includes a `json_schema` response format that can later be
sent through a supported Databricks Foundation Model API. Application-level
validation still checks citations and approval rules after model inference.

## Interview explanation

I treat prompt engineering as an application contract, not as informal text.
The system instructions establish the trust boundary, dynamic inputs are
encoded as untrusted data, structured output limits response shape, and
application validation prevents fabricated citations or unsafe escalation.
