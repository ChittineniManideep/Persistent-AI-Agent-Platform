# Agent Architecture — Multi-Step Persistent Workflow Design

## Why a RAG chatbot and this agent are architecturally different

A single-turn RAG chatbot has no state to persist: it embeds a query, retrieves, generates, done. This system is built around the opposite assumption — a goal decomposes into multiple dependent steps, each of which can fail independently, take meaningfully different amounts of time, and needs to survive the process that started it going away.

## The state machine

Every plan step has a status: `PENDING → RUNNING/RETRYING → COMPLETE` or `FAILED`. The executor (`backend/agent/executor.py`) only ever asks the plan "what's the next runnable step" — a step is runnable once its dependencies are `COMPLETE`. This is what makes resume trivial: reload the plan from storage, ask the same question, keep going. There's no separate "resume logic" distinct from "normal execution logic" — resuming *is* just calling `run()` again on a partially-completed plan.

## Failure handling: two distinct paths, not one generic retry

1. **Recoverable (transient) failures** — e.g. `web_search` timing out. Retried up to 3 times with exponential backoff. Most of these succeed on retry (proven in `backend/tests/test_agent.py::test_retry_recovers_from_transient_failure` — 30/30 trials completed despite ~15% per-call failure rate).
2. **Unrecoverable failures** — e.g. a calculation error that retrying can't fix. These mark the step `FAILED` immediately, halt the plan, and log a structured failure record rather than burning retry budget on something retrying won't solve. A production system would trigger re-planning here (not built in this version — flagged as the natural next extension, not silently glossed over).

## Checkpointing granularity

The plan is persisted to the session store **after every single step**, not just at plan completion. This is a deliberate choice: if the process dies mid-plan, at most one step's progress is lost, not the whole plan. The cost is more writes to the session store; the benefit is a resume that actually resumes close to where things stopped, which is the entire point of the "persistent across sessions" requirement.

## Why the gateway is a separate Node.js service, not just FastAPI WebSockets

The streaming gateway owns connection lifecycle (reconnect, backpressure) independently of agent execution. A client disconnecting doesn't tear down the backend session — the backend keeps running the plan in the background, and a reconnecting client (or the same client calling `/resume`) picks up from the session store. This separation is what makes "real-time streaming" and "persistent across sessions" compatible requirements rather than contradictory ones: the stream can drop without the underlying work being lost.

## What's genuinely simplified vs. a real production system

- The planner is rule-based for this demo (deterministic, testable) rather than LLM-driven — a real system would use LangChain to have an LLM decompose arbitrary goals; the state machine, executor, and persistence layer this ships with are unchanged either way, since the planner's job is just to produce a `Plan` object.
- Tools are mocked (simulated search results, simulated flaky failures) rather than calling real external APIs — the orchestration layer is the point being demonstrated, not building production search infrastructure.
- Redis is optional (in-memory fallback) so the project runs without external dependencies for review — the interface is identical either way, so swapping in real Redis is a one-line config change, not a rewrite.
