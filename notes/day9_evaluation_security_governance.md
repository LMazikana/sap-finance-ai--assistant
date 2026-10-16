# Day 9 — AI Evaluation, Security and Governance

## Controls implemented

- Response-schema validation
- Citation allow-list validation
- Answer-without-evidence prevention
- Basic prompt-injection detection
- Human approval for financial execution
- Append-only, idempotent audit events
- Hashed questions instead of raw prompt storage

## Evaluation results

- Test cases: 7
- Cases matching expectations: 7
- Pass rate: 100%
- Overall result: True
- Human-review requests: 2

## Challenge

I learned that Jupyter variables disappear after a kernel restart, while files previously written to disk remain available.

## Interview explanation

I implemented governance outside the language model. A deterministic validator checks grounding, citations, response structure and financial-action requests. Unsafe actions are routed to a human-approval queue, while audit events retain decision evidence without raw prompts.

## Future production enhancement

Migrate these deterministic checks into MLflow code-based
scorers, add groundedness and safety judges, and connect the
workflow to SAP Generative AI Hub content filtering and data
masking.
