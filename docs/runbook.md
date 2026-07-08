# NeuroFlow Architecture Runbook

This runbook is intended for on-call engineers responding to production incidents. It outlines the five most likely failure modes, how to verify them, and the explicit remediation steps to recover the system.

## Incident 1 — High query latency (P95 > 10s)

**Symptoms:**
- The P95 latency for the `POST /query` endpoint exceeds 10 seconds.
- User-facing RAG generation feels sluggish.

**Check:**
1. **Jaeger traces:** Open Jaeger and inspect the traces for the `query` endpoint. Identify whether the latency is in the `retrieval` span or the `generation` (LLM) span.
2. **Redis memory usage:** Check if Redis is evicting keys or thrashing. Look at the cache hit rate.
3. **Postgres query performance:** Run `SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 5;` to identify slow retrieval queries.

**Remediation:**
- **Cache saturation:** If Redis is full and thrashing, flush the Redis cache to force a clean slate, or provision more memory.
- **Database bottlenecks:** Add missing indexes to the `chunks` or `documents` table based on `pg_stat_statements`.
- **Compute constraints:** Scale up the API replica count if CPU utilization on the FastApi pods is pegged at 100%.

## Incident 2 — Evaluation scores degrading

**Symptoms:**
- MLflow or Prometheus alerts indicate that `eval_overall` has dropped below the acceptable baseline threshold.

**Check:**
1. **Scope:** Determine which specific pipeline and which metric (e.g., faithfulness, context precision) is dropping.
2. **Recent Data:** Check recently ingested documents. Low-quality, unstructured, or garbage input data will inevitably lead to low-quality retrieval and degraded scores.
3. **Model changes:** Check MLflow to see if a recent fine-tuning job replaced the active generation or embedding model.

**Remediation:**
- **Bad Model:** Immediately revert to the last known-good fine-tuned model via MLflow alias updates.
- **Bad Data:** Inspect the training/ingestion data quality. Delete garbage documents and trigger a re-index.

## Incident 3 — LLM provider circuit breaker open

**Symptoms:**
- Queries fail rapidly with 503 Service Unavailable.
- The system is dropping requests rather than waiting for the LLM.

**Check:**
1. **Circuit Breaker Status:** Hit `GET /health` and check the `circuit_breakers` block for `"state": "open"`.
2. **Provider Status:** Check the external provider's status page (e.g., OpenAI, Anthropic) to confirm an upstream outage.

**Remediation:**
- **Wait:** The circuit breaker is designed to auto-recover. Wait for the timeout to transition the breaker to `half-open` and then `closed`.
- **Manual Reset:** If the provider has resolved the issue but the breaker is stuck or the timeout is too long, manually reset it via `POST /admin/circuit-breaker/reset`.

## Incident 4 — Ingestion queue depth > 100

**Symptoms:**
- New documents are stuck in `queued` status forever.
- `GET /health` shows `queue_depth` steadily rising above 100.

**Check:**
1. **Queue Size:** Verify the depth via `GET /health`.
2. **Worker Logs:** Inspect the ARQ worker process logs for unhandled exceptions, out-of-memory (OOM) kills, or infinite loops.

**Remediation:**
- **Stuck Workers:** Restart the worker containers to clear any deadlocked processes.
- **Poison Pills:** Check Redis for stuck jobs that consistently crash the workers and manually drop those tasks from the queue.

## Incident 5 — Database disk usage > 80%

**Symptoms:**
- Postgres disk utilization triggers high-severity alerts.

**Check:**
1. **Growth Rate:** Identify which table is growing fastest (usually `evaluations` or `pipeline_runs`).
2. **Retention Jobs:** Check the logs to see whether old evaluations and runs are being successfully cleaned up by the daily retention job.

**Remediation:**
- **Manual Cleanup:** Run the data retention job manually to immediately reclaim disk space.
- **Vacuum:** Run a manual `VACUUM FULL` during a maintenance window if bloated rows are the cause.
