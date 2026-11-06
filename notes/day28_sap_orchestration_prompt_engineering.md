# Day 28 — SAP Orchestration and Prompt Controls

## Objective

Create a local configuration contract modeled on SAP AI Core Orchestration
Service V2, without using production credentials or calling an external model.

## Results

- Test cases: 5
- Provider-ready requests: 3
- Requests blocked before a model: 2
- Sensitive values masked: 2
- Valid structured outputs: 5
- External provider called: False

## Controls demonstrated

1. Runtime values are inserted through named prompt placeholders.
2. Email and IBAN values are anonymized before provider request creation.
3. Authorized policy context is filtered by role and business unit.
4. Prompt-injection phrases are blocked before model execution.
5. Answers require citations from the approved policy IDs.
6. Unsupported questions are refused.
7. Financial execution requests are escalated for human approval.
8. Audit events contain hashes and counts, not raw questions or PII.

## SAP alignment

The contract mirrors the V2 orchestration concepts of prompt templating,
model configuration, data masking, input/output filtering and grounding.
A production implementation must map this local contract to the installed
SAP Cloud SDK for AI V2 classes and a running orchestration deployment.

## Databricks alignment

The versioned prompt contract and deterministic test cases can later be
registered, evaluated and traced with MLflow. The current file-based version
is deliberately local so the control flow is understandable before adding
platform dependencies.

## Production gaps

- Replace the mock adapter with the SAP Orchestration Service V2 SDK.
- Replace phrase matching with configured enterprise content filters.
- Replace local regex masking with an approved data-privacy provider.
- Store prompt versions, traces and evaluation results in governed services.
- Keep production credentials outside notebooks and Git.

## Interview explanation

I separated prompt design from runtime data. Before a Finance request reaches
a model, the application authorizes its context, anonymizes sensitive values
and blocks injection attempts. The response must follow a fixed schema, cite
only approved policies and escalate transaction execution to a human. The
audit trail records control outcomes without retaining the raw prompt.
