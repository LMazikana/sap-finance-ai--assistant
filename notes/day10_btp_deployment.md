# Day 10 — SAP BTP Deployment Readiness

## What I built

- Flask API for the governed finance assistant
- Cloud Foundry health endpoint
- Governed finance-question endpoint
- Dynamic PORT configuration
- Python buildpack manifest
- Gunicorn production start command
- Python runtime configuration
- Deployment exclusion rules
- API contract tests
- Deployment credential scan

## API behavior

- Informational request: answer with citations
- Financial action: escalate for human approval
- Unauthorized role: refuse
- Invalid request: return HTTP 400
- Governance failure: block the response

## Test results

- Health test: 200
- Information test: 200
- Financial action test: 202
- Unauthorized-role test: 200
- Security findings: 0

## Challenge

The main challenge was separating deployment configuration from application logic while preserving governance controls.

## Interview explanation

I packaged a governed SAP Finance assistant as a Flask API for SAP BTP Cloud Foundry. The service exposes health and finance-question endpoints, uses the platform-assigned port, applies role-aware retrieval and governance validation, escalates financial execution for human approval, and emits privacy-conscious audit events.

## Next production enhancements

- Bind the application to SAP AI Core.
- Replace deterministic generation with Generative AI Hub orchestration.
- Add enterprise authentication and authorization.
- Send audit events to centralized application logging.
- Add CI/CD and deployment approval controls.
