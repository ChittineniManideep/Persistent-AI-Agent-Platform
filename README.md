# Persistent AI Agent Platform
### A full-stack, production-shaped multi-step agent system — Next.js chat UI, Node.js streaming gateway, FastAPI/LangChain agent backend with session persistence and failure recovery, PyTorch reranker, and Kubernetes deployment


| Gap | Where it's addressed |
|---|---|
| Frontend (React/Next.js) — listed as a skill, no project | `frontend/` — real Next.js chat UI with streaming |
| Kubernetes | `k8s/` — deployments, service, StatefulSet, HPA |
| PyTorch (had TensorFlow/Keras) | `ml/reranker_model.py` — trained cross-encoder reranker |
| Node.js | `streaming-gateway/` — WebSocket streaming gateway |
| Production agent failure/recovery/observability | `backend/agent/executor.py`, `backend/observability/` |
| **Multi-step persistent agent workflow (core requirement)** | `backend/agent/planner.py`, `backend/agent/session_store.py` |
| Real-time streaming with latency constraints | `streaming-gateway/server.js`, latency budget tracked in `backend/observability/tracing.py` |

## Architecture

```
Next.js frontend (streaming chat UI)
        │  WebSocket
        ▼
Node.js streaming gateway (connection mgmt, backpressure, reconnect)
        │  internal HTTP/SSE
        ▼
FastAPI agent backend
   ├── Planner   — decomposes a goal into a step sequence
   ├── Executor  — runs steps, retries on tool failure, checkpoints state
   ├── Tools     — search, calculator, structured-data lookup (extensible)
   └── Session store — Redis-backed, survives process restart / reconnect
        │
        ▼
PyTorch reranker (improves tool-result relevance before the agent reasons over it)
```

The core design decision: **the agent's state lives outside the request/response cycle.** A session can be interrupted (client disconnect, gateway restart, backend redeploy) and resumed from its last checkpoint — this is what "multi-step persistent agent workflow" actually means in production, versus a RAG chatbot that re-derives everything from scratch each turn.

## Repo structure

```
persistent-ai-agent-platform/
├── README.md
├── backend/                    # FastAPI + LangChain agent
│   ├── agent/
│   │   ├── planner.py          # Goal → step plan decomposition
│   │   ├── tools.py            # Tool definitions (search, calculator, lookup)
│   │   ├── executor.py         # Step execution, retry/backoff, checkpointing
│   │   └── session_store.py    # Persistent session state (Redis-backed)
│   ├── observability/
│   │   └── tracing.py          # Per-step tracing, failure logging, latency budget
│   ├── main.py                 # FastAPI app, SSE streaming endpoint
│   └── tests/test_agent.py
├── ml/
│   └── reranker_model.py       # PyTorch cross-encoder reranker, trained + evaluated
├── streaming-gateway/          # Node.js WebSocket gateway
│   ├── server.js
│   └── package.json
├── frontend/                   # Next.js chat UI
│   ├── app/page.tsx
│   ├── components/ChatStream.tsx
│   └── package.json
├── k8s/                        # Kubernetes manifests
│   ├── backend-deployment.yaml
│   ├── gateway-deployment.yaml
│   ├── frontend-deployment.yaml
│   ├── redis-statefulset.yaml
│   └── hpa.yaml
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.gateway
│   └── Dockerfile.frontend
└── docs/
    ├── agent_architecture.md
    └── observability_and_slo.md
```
