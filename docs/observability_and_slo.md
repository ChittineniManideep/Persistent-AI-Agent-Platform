# Observability & Latency Budget

## Per-step tracing

Every tool call gets a `Span` (`backend/observability/tracing.py`): start time, end time, success/failure, latency, and whether it breached its latency budget. This is what makes an agent failure debuggable after the fact — "which step, which attempt, how long, what error" — rather than a single opaque "the agent failed" log line.

## Latency budgets per tool

| Tool | Budget (ms) | Rationale |
|---|---|---|
| `web_search` | 2000 | External dependency, most latency-tolerant step |
| `rerank` | 500 | Local PyTorch inference, should be fast |
| `extract_facts` | 1500 | LLM call in a real system — allow for generation time |
| `summarize` | 1500 | LLM call — same rationale |
| default | 1000 | Conservative default for any tool not explicitly budgeted |

A span exceeding its budget is flagged (`over_budget: true`) but does not fail the step — the point is visibility into where a real-time streaming experience is degrading, not false-failing a slow-but-successful call.

## What the trace summary reports

`AgentTracer.summary()` returns: total tool calls, successful vs. failed, retry count, spans over budget, unrecoverable failures, and average latency — the minimum viable observability output for an agent system, enough to answer "is this session healthy" and "where is it spending time" without reading every individual span.

## Gateway-level latency visibility

The Node.js gateway timestamps every event it forwards from the backend to the client (`gateway_elapsed_ms` in `streaming-gateway/server.js`), separate from the backend's own per-step latency. This distinguishes two different failure modes:

- **Backend is slow** — a specific step's span shows high latency in the trace
- **Network/gateway is slow** — the gap between the backend emitting an event and the gateway forwarding it grows, even though individual backend spans look fine

Conflating these two would make debugging a production latency issue guesswork; keeping them separate makes it a lookup.

## Backpressure handling

If a client's WebSocket send buffer backs up (slow network, backgrounded tab), the gateway drops intermediate step-progress events rather than let memory grow unbounded — but never drops the final `complete` event, so the client always eventually learns the outcome even if it missed some progress updates. This is a deliberate trade-off (some progress visibility lost) rather than either crashing the gateway or blocking backend execution on a slow client.
