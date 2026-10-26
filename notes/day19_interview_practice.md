# Day 19 — Interview Practice

## Question 1: Walk me through the solution you built

I built a governed SAP Finance assistant using synthetic enterprise policy
data. A release gate is checked first. Retrieval filters policy chunks by role
and company code. Citations are validated against retrieved context, execution
requests require human approval and the workflow creates privacy-safe traces.

## Question 2: How do you reduce hallucination and data leakage?

Answers are constrained to retrieved context, and model citations must be a
subset of retrieved citations. Access filtering happens before generation.
Restricted requests are refused, and audit evidence stores a query hash rather
than the raw question.

## Question 3: Why is human approval required?

Posting, approving or reversing entries can affect financial reporting. The
assistant therefore remains advisory and escalates execution requests to an
authorized human, preserving segregation of duties.

## Question 4: How would you productionize it?

On Databricks, I would use Unity Catalog, Vector Search, Model Serving and
MLflow. In SAP, I would use Generative AI Hub and deploy on BTP. Credentials
would come from service bindings, not source code.

## Evidence

- Governance: 6/6
- Deployment: 11/11
- End-to-end demo: 4/4

## Self-review

- Total score out of 8:
- Strongest answer:
- Weakest answer:
- One explanation to simplify:
