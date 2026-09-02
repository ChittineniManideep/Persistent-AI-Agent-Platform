"""
Agent observability — per-step span tracing, latency budget tracking
against the real-time streaming constraint, and structured failure
logging. This is what makes agent failures debuggable in production
rather than a silent retry loop nobody can inspect afterward.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# Latency budget: the JD requires real-time streaming with latency
# constraints — this is where that requirement actually gets enforced
# and measured, not just claimed
STEP_LATENCY_BUDGET_MS = {
    "web_search": 2000,
    "rerank": 500,
    "extract_facts": 1500,
    "summarize": 1500,
    "default": 1000,
}


@dataclass
class Span:
    span_id: str
    session_id: str
    plan_id: str
    step_id: str
    tool_name: str
    attempt: int
    start_time: float
    end_time: Optional[float] = None
    success: Optional[bool] = None
    error: Optional[str] = None
    latency_ms: Optional[float] = None
    over_budget: Optional[bool] = None


class AgentTracer:
    def __init__(self):
        self.spans: list[Span] = []
        self.unrecoverable_failures: list[dict] = []

    def start_span(self, session_id, plan_id, step_id, tool_name, attempt) -> Span:
        span = Span(
            span_id=str(uuid.uuid4())[:8], session_id=session_id, plan_id=plan_id,
            step_id=step_id, tool_name=tool_name, attempt=attempt, start_time=time.time(),
        )
        self.spans.append(span)
        return span

    def end_span(self, span: Span, success: bool, error: str = None):
        span.end_time = time.time()
        span.success = success
        span.error = error
        span.latency_ms = round((span.end_time - span.start_time) * 1000, 2)
        budget = STEP_LATENCY_BUDGET_MS.get(span.tool_name, STEP_LATENCY_BUDGET_MS["default"])
        span.over_budget = span.latency_ms > budget

    def log_unrecoverable_failure(self, session_id: str, step_id: str, reason: str):
        self.unrecoverable_failures.append({
            "session_id": session_id, "step_id": step_id, "reason": reason, "timestamp": time.time(),
        })

    def summary(self) -> dict:
        completed = [s for s in self.spans if s.success is True]
        failed = [s for s in self.spans if s.success is False]
        over_budget = [s for s in self.spans if s.over_budget]
        return {
            "total_spans": len(self.spans),
            "successful_calls": len(completed),
            "failed_calls": len(failed),
            "retries": len([s for s in self.spans if s.attempt > 1]),
            "spans_over_latency_budget": len(over_budget),
            "unrecoverable_failures": len(self.unrecoverable_failures),
            "avg_latency_ms": round(sum(s.latency_ms for s in self.spans) / len(self.spans), 2) if self.spans else 0,
        }
