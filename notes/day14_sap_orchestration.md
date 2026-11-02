# Day 14 — SAP Orchestration V2 Adapter

## Objective

Build a credential-free SAP Generative AI Hub Orchestration V2
request adapter for the governed SAP Finance assistant.

## What I built

- An inline Orchestration V2 request builder.
- Separate system instructions and runtime placeholder values.
- Structured JSON response configuration.
- Validation for decisions, citations and human approval.
- A check preventing credential fields from entering the payload.
- Local mock-response tests requiring no SAP credentials.

## Governance decision

The assistant may explain approved Finance policies, but it cannot
approve, post, reverse or modify a financial transaction. Requests
for execution are escalated to an authorized human approver.

## Test result

6 of 6 tests passed.

## Production next step

Replace the mock response with an authenticated SAP Orchestration V2
client. Credentials must come from an approved secret store or bound
service, not source code, notebooks, request files or Git.

## Interview explanation

I created a provider adapter that converts governed Finance prompts
into an SAP Orchestration V2 request. User questions and retrieved
policy context remain runtime data rather than system instructions.
The response is accepted only after its structure and human-approval
rules pass deterministic validation.
