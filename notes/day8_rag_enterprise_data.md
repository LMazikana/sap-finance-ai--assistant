# Day 8 — Citation-ready RAG

## What I built

- Converted finance policies into retrieval chunks.
- Added policy IDs, citations and role metadata.
- Filtered evidence before prompt construction.
- Connected retrieved evidence to the versioned prompt.
- Evaluated retrieval with four test cases.

## Results

- Chunks created: 3
- Recall@3: 1.00
- Citation integrity passed: True
- Overall evaluation passed: True

## Challenge

Replace this sentence with one difficulty you encountered.

## Interview explanation

I built a citation-ready retrieval pipeline for synthetic SAP Finance policies. Each chunk carries its policy ID, source citation and allowed roles. The application filters unauthorized chunks before constructing the LLM prompt, then evaluates retrieval recall, citation integrity and out-of-scope behavior.
