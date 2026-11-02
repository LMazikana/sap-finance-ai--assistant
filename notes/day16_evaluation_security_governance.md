# Day 16 — AI Evaluation, Security and Governance

## Objective

Create a repeatable governance evaluation and release gate for the
role-aware SAP Finance assistant.

## Evaluation coverage

- Expected-policy retrieval
- Forbidden-policy leakage
- Response-schema validation
- Citation validity
- Decision correctness
- Human-approval enforcement
- Financial-transaction escalation
- Audit-log privacy

## Evaluation result

- Cases passed: 6/6
- Case pass rate: 100%
- Retrieval pass rate: 100%
- Citation validity: 100%
- Decision accuracy: 100%
- Human-approval accuracy: 100%
- Audit privacy: 100%
- Security leakage events: 0
- Invented citation detected: True

## Release decision

APPROVED_FOR_LOCAL_DEMO

This decision approves only the local portfolio demonstration.
Production deployment would additionally require live model evaluation,
penetration testing, privacy review, model monitoring, approved
credentials, infrastructure approval and business-owner sign-off.

## Databricks production mapping

The JSON evaluation dataset maps to an MLflow Evaluation Dataset.
The deterministic checks map to MLflow code-based scorers.
Groundedness, relevance, safety and correctness can later be assessed
with built-in or custom LLM judges. Results can be tracked through
MLflow and governed with Unity Catalog.

## Interview explanation

I created a risk-based evaluation gate instead of evaluating only
answer quality. The gate checks retrieval authorization, citation
grounding, decision accuracy, human approval and audit privacy. It also
contains a negative control with an invented citation, proving that
the evaluator can detect a known failure rather than merely producing
passing scores.
