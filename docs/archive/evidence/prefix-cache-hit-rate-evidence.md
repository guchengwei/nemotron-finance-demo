# Prefix Cache Hit Rate Evidence

Written on 2026-03-19 UTC for follow-up investigation.

## Executive Summary

- Report generation works in automated e2e.
- vLLM was restarted with `--enable-prefix-caching`.
- A forced real `/api/report/generate` run still showed `Prefix cache hit rate: 0.0%` in vLLM logs.
- A second `/api/report/generate` for the same run did not hit vLLM at all because backend DB caching returned the stored report.

## What Was Verified

### 1. Automated e2e-style report generation works

The backend e2e-style test file passed:

```bash
cd backend
python -m pytest --tb=short -q tests/test_report_generate_e2e.py
```

Observed result:

```text
2 passed in 24.36s
```

What that test covers:

- seeds personas with nested `financial_extension.financial_literacy`
- calls `/api/report/generate`
- asserts `top_picks` has 3 valid UUIDs
- asserts `demographic_breakdown.by_financial_literacy` is non-empty
- asserts the second call returns cached report data
- covers both small and large survey sizes

### 2. Real report generation also works

A real completed run in `data/history.db` was used:

```text
28e1033e-a2f3-4418-a1b2-815dfc43bbf7
```

To force regeneration, `survey_runs.report_json` was set to `NULL` for that run. Then:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/report/generate \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"28e1033e-a2f3-4418-a1b2-815dfc43bbf7"}'
```

Observed:

- HTTP 200 from backend
- response contained 3 `top_picks`
- backend log showed 3 sequential `POST http://localhost:8000/v1/chat/completions`

## vLLM Runtime Configuration

The previous vLLM process on port `8000` did not include prefix caching.

Its command line was:

```text
/usr/bin/python /usr/local/bin/vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese --host 0.0.0.0 --port 8000 --trust-remote-code --max-model-len 131072 --max-num-seqs 64 --gpu-memory-utilization 0.90 --reasoning-parser-plugin nemotron_nano_v2_reasoning_parser.py --reasoning-parser nemotron_nano_v2 --mamba-ssm-cache-dtype float32
```

It was restarted with:

```text
/usr/bin/python /usr/local/bin/vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese --host 0.0.0.0 --port 8000 --trust-remote-code --max-model-len 131072 --max-num-seqs 64 --gpu-memory-utilization 0.90 --reasoning-parser-plugin nemotron_nano_v2_reasoning_parser.py --reasoning-parser nemotron_nano_v2 --mamba-ssm-cache-dtype float32 --enable-prefix-caching
```

During startup, vLLM logged:

```text
enable_prefix_caching': True
Warning: Prefix caching is currently enabled. Its support for Mamba layers is experimental.
```

## Evidence For 0.0% Prefix Cache Hit Rate

After the forced real report generation, the live vLLM session logged:

```text
INFO:     127.0.0.1:40084 - "POST /v1/chat/completions HTTP/1.1" 200 OK
INFO 03-19 09:11:18 [loggers.py:257] Engine 000: Avg prompt throughput: 204.4 tokens/s, Avg generation throughput: 49.9 tokens/s, Running: 1 reqs, Waiting: 0 reqs, GPU KV cache usage: 0.4%, Prefix cache hit rate: 0.0%
INFO:     127.0.0.1:48598 - "POST /v1/chat/completions HTTP/1.1" 200 OK
INFO:     127.0.0.1:48608 - "POST /v1/chat/completions HTTP/1.1" 200 OK
INFO 03-19 09:11:28 [loggers.py:257] Engine 000: Avg prompt throughput: 371.8 tokens/s, Avg generation throughput: 69.9 tokens/s, Running: 0 reqs, Waiting: 0 reqs, GPU KV cache usage: 0.0%, Prefix cache hit rate: 0.0%
```

Important observations:

- The report-generation flow did make 3 real model calls after prefix caching was enabled.
- vLLM still reported `Prefix cache hit rate: 0.0%`.
- This evidence was collected after a clean forced regeneration, not from a backend-cached response.

## Backend Cache Behavior

Immediately after the first forced regeneration, a second identical backend request was made:

```bash
curl -sS -X POST http://127.0.0.1:8080/api/report/generate \
  -H 'Content-Type: application/json' \
  -d '{"run_id":"28e1033e-a2f3-4418-a1b2-815dfc43bbf7"}'
```

Observed:

- backend returned `200`
- same report payload came back
- backend log only showed the `/api/report/generate` response
- no new vLLM `/v1/chat/completions` entries were emitted

This means:

- backend DB caching is working
- repeated backend requests for the same completed run will not exercise vLLM prefix caching unless `report_json` is cleared first

## Additional Real-Run Observation

For the same real run used above, the regenerated report contained:

```text
demographic_breakdown.by_financial_literacy = {}
```

This was true in both:

- the live API response
- the persisted `survey_runs.report_json`

That differs from the automated e2e test, which expects this field to be non-empty for synthetic seeded personas with nested `financial_extension`.

## Current Process State At Time Of Capture

- Backend health endpoint was healthy:

```json
{"status":"ok","mock_llm":false,"llm_reachable":true}
```

- vLLM `/v1/models` responded successfully after restart.
- The active vLLM process was serving on port `8000` with prefix caching enabled.

## Constraints For Future Investigation

- Do not use repeated `/api/report/generate` calls on an already-cached run as evidence for prefix-cache behavior. Backend caching masks model activity.
- Use a run with `report_json = NULL`, or clear it before each measurement.
- Capture both backend logs and vLLM logs in the same observation window.
