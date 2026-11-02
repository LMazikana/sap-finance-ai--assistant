# Day 20 — Resilient Model API Calls

## Objective

Add a reliable, provider-neutral API boundary to the governed SAP Finance
assistant.

## What I implemented

- Bounded retries for HTTP 429, 500, 502, 503 and 504.
- Retry handling for timeouts and connection errors.
- Fail-fast behavior for non-retryable errors such as HTTP 401.
- Correlation and idempotency identifiers.
- Normalized success and failure envelopes.
- Question hashing and credential redaction in audit events.
- Six deterministic tests requiring no live API credentials.

## Results

- Tests passed: 6/6
- Generated module: `app/resilient_model_client.py`
- Generated evidence: `tests/day20_api_resilience_results.json`

## Architecture decision

The finance application depends on a provider-neutral client instead of
calling a model endpoint directly. A later adapter can connect the same
application to Databricks Model Serving or SAP Generative AI Hub while
preserving consistent retry, error and audit behavior.

## Interview explanation

I built the API boundary around the model, not merely a model call. The
client distinguishes temporary failures from permanent failures, preserves
one request ID across retries, prevents unlimited retries, and records
privacy-aware audit evidence. This improves reliability without weakening
financial governance.
