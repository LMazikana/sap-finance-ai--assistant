# Day 27 — Async API Resilience and Idempotency

## Objective

Add asynchronous request handling, idempotency protection, provider
timeouts and concurrency limits to the governed SAP Finance assistant.

## Results

- Incoming requests: 5
- Unique idempotency keys: 4
- Provider calls executed: 4
- Duplicate provider calls avoided: 1
- Maximum concurrent calls: 2
- Timeout responses: 1

## Controls implemented

1. Duplicate requests with the same idempotency key share one in-flight task.
2. Successful results are cached for later duplicate requests.
3. Timed-out requests are not cached.
4. A semaphore limits simultaneous provider usage.
5. Slow providers return a controlled refusal rather than an invented answer.
6. Transaction execution continues to require human approval.
7. Audit events contain a hashed idempotency key and no raw question.

## Databricks alignment

The gateway models client-side controls needed when calling model-serving
or agent endpoints: bounded concurrency, timeout handling, safe repetition
and latency measurement.

## SAP alignment

SAP Cloud SDK for AI supports asynchronous orchestration calls and request
timeouts. The simulated provider can later be replaced by an SAP
orchestration `arun` call without changing the gateway contract.

## Production limitation

The cache is currently in memory and is local to one Python process.
A scaled SAP BTP or Databricks deployment would need a shared persistent
idempotency store such as Redis, a database or a governed Delta table.

## Interview explanation

I prevented duplicate Finance requests from generating duplicate provider
calls by assigning each logical operation an idempotency key. Concurrent
duplicates join the same in-flight task, provider concurrency is bounded,
and slow requests fail safely without generating unsupported guidance.
