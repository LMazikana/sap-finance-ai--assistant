# Day 13 — Python and API Model-Provider Boundary

## Objective

Create a typed provider-neutral interface between the governed SAP Finance application and future foundation-model services.

## Components created

- `ChatMessage` validates system, user and assistant messages.
- `ModelRequest` standardizes messages and model parameters.
- `ModelResponse` normalizes provider responses.
- `ModelProvider` defines the adapter contract.
- Explicit exceptions distinguish transient and permanent failures.
- `RetryPolicy` applies bounded exponential backoff.
- `ProviderExecution` records attempts, delays and latency.

## Why this design matters

Retrieval, governance, citations, approvals and audit logging should not depend on a particular model vendor. A provider adapter can translate the internal request into SAP Generative AI Hub, Databricks Model Serving or another compatible API.

## Reliability behavior tested

- Tests executed: 6
- Tests passed: 6
- Tests failed: 0
- Permanent errors were not retried.
- Transient errors and timeouts were retried.
- Retry exhaustion stopped after the configured maximum.
- No network calls or real waiting occurred.

## Current limitation

The provider boundary is complete, but it does not yet contain a live SAP AI Core adapter. That adapter will be created next using a credential-free mock payload before any real connection.

## Interview explanation

I separated the finance assistant's business and governance logic from its model provider. I defined typed request and response contracts, classified transient and permanent errors, and added bounded exponential retries. This allows the same governed application to use SAP Generative AI Hub or Databricks Model Serving without rewriting its retrieval and control layers.
