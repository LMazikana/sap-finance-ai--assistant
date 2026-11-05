# Day 26 — Interview Drill and Model Answers

## Q1: Walk me through the architecture of your governed SAP Finance AI assistant.

The request enters a FastAPI service where its schema and role are validated. The retrieval layer selects only policy context authorized for that role and business unit. The assistant returns a structured answer with policy citations, refuses unsupported questions and escalates transaction execution to a human. Evaluation, release gates and audit traces provide evidence across the lifecycle.

**My score:** 4

## Q2: How does your design reduce hallucination and unsupported Finance guidance?

I constrain the assistant to authorized retrieved context, require citations from that context and validate an exact output schema. When evidence is unavailable, the correct behavior is refusal rather than generation from general model knowledge. Regression tests detect unsupported facts, invented citations and restricted-data leakage.

**My score:** 3

## Q3: What happens when a user asks the assistant to post, approve or reverse a financial transaction?

The assistant does not receive authority to execute Finance transactions. It returns an escalation decision, sets the human-approval indicator and records the request in the audit trail. The responsible Finance approver remains the accountable decision-maker.

**My score:** 3

## Q4: How do you determine whether a new prompt or model version can be released?

Every candidate is tested against the same evaluation set. I score schema compliance, grounding, citation integrity, access leakage, refusal and approval behavior. Critical failures block the technical gate. Even after the technical gate passes, production authorization remains a separate human governance decision.

**My score:** 5

## Q5: How does this project combine SAP and Databricks capabilities?

SAP Business Data Cloud supplies governed enterprise data and business semantics. SAP Generative AI Hub provides model orchestration and controls such as grounding, masking and filtering, while SAP BTP hosts the API. Databricks and MLflow provide evaluation, tracing, human feedback and governance through Unity Catalog.

**My score:** 5
