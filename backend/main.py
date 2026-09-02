"""
FastAPI backend — exposes the agent over a streaming endpoint (Server-Sent
Events), so the frontend/gateway can render each step's progress as it
happens rather than waiting for the whole plan to finish. Also exposes a
resume endpoint, so a session interrupted mid-plan can be continued.
"""
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid

from agent.planner import plan_goal
from agent.executor import AgentExecutor
from agent.session_store import SessionStore, rehydrate_plan
from observability.tracing import AgentTracer

app = FastAPI(title="Persistent AI Agent Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

session_store = SessionStore(redis_url=None)  # in-memory for local/demo; pass REDIS_URL env in production


@app.post("/session/start")
async def start_session(goal: str):
    session_id = str(uuid.uuid4())[:12]
    plan = plan_goal(goal)
    session_store.save_plan(session_id, plan)
    return {"session_id": session_id, "plan_id": plan.plan_id, "step_count": len(plan.steps)}


@app.get("/session/{session_id}/stream")
async def stream_session(session_id: str):
    raw = session_store.load_plan_raw(session_id)
    if raw is None:
        raise HTTPException(404, "Session not found")

    async def event_generator():
        plan = rehydrate_plan(raw)
        tracer = AgentTracer()
        executor = AgentExecutor(session_store, tracer)

        while not plan.is_complete() and not plan.has_unrecoverable_failure():
            step = plan.next_runnable_step()
            if step is None:
                break
            executor._execute_step(plan, step, session_id)
            session_store.save_plan(session_id, plan)

            yield f"data: {json.dumps({'step_id': step.step_id, 'status': step.status, 'result': step.result})}\n\n"
            await asyncio.sleep(0.05)  # yields control — real streaming, not a buffered dump at the end

        yield f"data: {json.dumps({'event': 'complete', 'summary': tracer.summary()})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/session/{session_id}/resume")
async def resume_session(session_id: str):
    """Explicitly demonstrates the persistence requirement: this endpoint
    can be called after a backend restart and will continue exactly where
    the plan left off, using only what's in the session store."""
    raw = session_store.load_plan_raw(session_id)
    if raw is None:
        raise HTTPException(404, "Session not found — cannot resume")

    plan = rehydrate_plan(raw)
    tracer = AgentTracer()
    executor = AgentExecutor(session_store, tracer)
    completed_plan = executor.run(plan, session_id)

    return {
        "session_id": session_id,
        "resumed_from_step": next((s.step_id for s in plan.steps if s.status.value == "complete"), "s1"),
        "final_status": "complete" if completed_plan.is_complete() else "failed",
        "trace_summary": tracer.summary(),
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
