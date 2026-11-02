# Day 15 — Role-Aware Enterprise RAG

## Objective

Prevent unauthorized Finance policy chunks from entering an LLM
prompt by applying role and company-code filters before ranking.

## What I built

- A synthetic enterprise Finance chunk catalog.
- Policy, chunk, source and business-domain metadata.
- Role-aware and company-code-aware access filtering.
- Local vector ranking using term frequencies and cosine similarity.
- Stable source citations using policy ID and chunk ID.
- Retrieval audit evidence that hashes rather than stores the question.
- Integration with the SAP Orchestration V2 request adapter.

## Security sequence

1. Validate the retrieval request.
2. Filter chunks by user role.
3. Filter chunks by company code.
4. Rank only the remaining authorized chunks.
5. Add only those chunks to the model prompt.
6. Preserve citations for response validation and audit.

## Test result

7 of 7 retrieval tests passed.

## Databricks production mapping

The local chunk catalog represents a governed Delta table.
The local vector calculation represents an AI Search query.
Role and company-code checks represent metadata filters and
Unity Catalog-governed access controls.

## Interview explanation

I implemented security-trimmed RAG for a Finance assistant. Access
filters run before similarity ranking, which prevents unauthorized
content from entering the prompt even if it is semantically relevant.
Every returned chunk carries a stable citation, and the retrieval audit
stores operational evidence without retaining the complete question.
