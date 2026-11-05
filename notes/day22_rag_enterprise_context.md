# Day 22 — Governed Enterprise Context

## Purpose

This implementation converts retrieved finance candidates into an authorized, bounded and citation-ready context package.

## Governance sequence

1. Validate the requesting role.
2. Enforce company-code access.
3. Allow only approved classifications.
4. Reject unapproved or duplicate content.
5. Detect prompt injection in questions and documents.
6. Score only authorized candidates for relevance.
7. Apply a bounded context token budget.
8. Preserve citations and source lineage.
9. Block generation when no authorized context remains.

## Privacy and security

The saved package stores a hash of the question instead of using the raw question as audit metadata.

## Key evidence

- `data/day22_retrieved_candidates.json`
- `app/governed_context_builder.py`
- `artifacts/day22_approved_context_package.json`
- `tests/day22_governed_context_results.json`

## Result

The authorized journal-entry scenario produces grounded context with citation `FIN-JE-001`. Restricted, cross-company and malicious content is excluded before generation.
