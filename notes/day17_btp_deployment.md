# Day 17 — SAP BTP Deployment Readiness

## Objective

Package the governed SAP Finance assistant for review before deployment
to SAP BTP Cloud Foundry.

## What I built

- A Flask-based BTP runtime module.
- A liveness endpoint at `/health`.
- A governance-aware readiness endpoint at `/ready`.
- A sanitized governance-status endpoint.
- A Cloud Foundry application manifest.
- A Gunicorn production start command.
- A deployment secret scan.
- Artifact fingerprints for traceability.
- A deployment-readiness audit event.

## Governance behavior

The process can remain alive while the application is not ready.
The `/health` endpoint confirms process liveness. The `/ready`
endpoint returns HTTP 200 only when the governance release gate exists,
is valid and contains an approved decision with all checks passing.

## Credential design

SAP AI Core credentials are not stored in the notebook, source code,
Git repository or deployment manifest. Production credentials should
be supplied using SAP BTP service bindings and read from the bound
service environment at runtime.

## Readiness result

- Checks passed: 11/11
- Secret findings: 0
- Decision: READY_FOR_BTP_DEPLOYMENT_REVIEW

## Interview explanation

I separated application liveness from governance readiness. A running
process is not automatically allowed to receive traffic. The readiness
endpoint evaluates a signed-off release artifact, while the deployment
validator checks the Cloud Foundry manifest, runtime dependencies,
health endpoints, credentials policy and artifact fingerprints. This
creates a traceable promotion control between evaluation and deployment.
