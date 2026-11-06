# Day 24 — SAP BTP Integration and Deployment

## Objective

Package the governed SAP Finance assistant as a Python HTTP API
suitable for future SAP BTP Cloud Foundry deployment.

## API endpoints

- `/health` confirms that the application process is operating.
- `/ready` confirms that the automated technical gate passed.
- `/configuration` reports configuration presence without exposing values.
- `/ask` returns governed Finance decisions and creates audit events.

## Governance behavior

- The technical gate is `PASS`.
- Human approval is `PENDING`.
- Deployment authorization is `False`.
- Production requests are blocked until deployment authorization is true.
- Transaction-execution requests are escalated for human approval.
- Audit logging stores a question hash instead of the raw question.

## SAP BTP design

Cloud Foundry will use the Python buildpack, the platform-provided
PORT and the `/health` endpoint. SAP AI Core credentials will be
provided through environment variables or bound services rather
than committed to GitHub.

## Current limitation

This version uses deterministic synthetic responses. It does not
yet call SAP Generative AI Hub. The next integration step is to
replace the deterministic response generator with the SAP Cloud
SDK for AI while preserving the same governance contract.

## Interview explanation

I separated application health, technical readiness and deployment
authorization. This prevents a technically functioning AI service
from receiving production Finance traffic before governance
approval is recorded.
