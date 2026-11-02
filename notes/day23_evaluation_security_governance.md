# Day 23 — Evaluation, Security, and Governance

## Objective

Compare an unsafe baseline finance assistant with a hardened
candidate using the same repeatable governance evaluation dataset.

## Evaluation dimensions

- Exact output-schema compliance
- Citation integrity
- Grounded fact coverage
- Role-aware access control
- Human-approval escalation
- Refusal when authorized evidence is unavailable
- Decision and approval-flag consistency

## Results

| Candidate | Technical gate | Case pass rate | Check pass rate |
|---|---:|---:|---:|
| baseline-v1 | BLOCK | 16.7% | 81.0% |
| hardened-v2 | PASS | 100.0% | 100.0% |

## Baseline failures detected

The evaluator detected restricted-data leakage, unsafe transaction
execution, unsupported answers, invented citations, and an invalid
output schema.

## Governance decision

The hardened candidate passed the automated technical gate.
Human approval remains PENDING and deployment_authorized remains
False. Automated evaluation supplies evidence; it does not replace
the accountable finance or AI governance approver.

## Databricks alignment

The JSON test records represent a local prototype of an MLflow
evaluation dataset. The deterministic checks can later be migrated
to custom MLflow scorers, with the results stored and governed in
Unity Catalog.

## SAP alignment

The exercise applies layered controls around grounding, role-aware
access, output validation, human-in-the-loop approval, and secure
audit logging.
