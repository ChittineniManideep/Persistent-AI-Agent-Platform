"""
Agent executor — runs a plan step by step, with retry/backoff on
recoverable tool failures, checkpointing progress to the session store
after every step (not just at the end), and a distinct path for
unrecoverable failures that require re-planning rather than retrying.

This is the piece that actually answers "production agent failure/
recovery/observability patterns" — a portfolio RAG demo typically has
none of this, because a single-turn Q&A has nothing to checkpoint.
"""
import time
from .planner import Plan, PlanStep, StepStatus
from .tools import TOOL_REGISTRY, ToolExecutionError
from .session_store import SessionStore
from observability.tracing import AgentTracer


class UnrecoverableStepError(Exception):
    """Raised when a step fails in a way retrying cannot fix — the
    executor surfaces this to the caller rather than looping forever."""
    pass


class AgentExecutor:
    MAX_RETRIES = 3
    BACKOFF_BASE_SECONDS = 0.2  # kept small for test speed; would be 1-2s in production

    def __init__(self, session_store: SessionStore, tracer: AgentTracer):
        self.session_store = session_store
        self.tracer = tracer

    def run(self, plan: Plan, session_id: str) -> Plan:
        """Executes a plan to completion, or as far as it can get before
        hitting an unrecoverable failure. Can be called again with a
        partially-completed plan (loaded from session_store) to resume."""
        self.session_store.save_plan(session_id, plan)

        while not plan.is_complete() and not plan.has_unrecoverable_failure():
            step = plan.next_runnable_step()
            if step is None:
                break  # no runnable step and not complete — a dependency cycle or all remaining steps blocked

            self._execute_step(plan, step, session_id)
            self.session_store.save_plan(session_id, plan)  # checkpoint after EVERY step

        return plan

    def _execute_step(self, plan: Plan, step: PlanStep, session_id: str):
        step_context = {
            s.step_id: s.result for s in plan.steps if s.status == StepStatus.COMPLETE
        }
        tool_fn = TOOL_REGISTRY[step.tool_name]

        for attempt in range(1, self.MAX_RETRIES + 1):
            step.attempt_count = attempt
            step.status = StepStatus.RUNNING if attempt == 1 else StepStatus.RETRYING
            span = self.tracer.start_span(session_id, plan.plan_id, step.step_id, step.tool_name, attempt)

            try:
                result = tool_fn(step_context=step_context, **step.tool_input)
                step.result = result
                step.status = StepStatus.COMPLETE
                self.tracer.end_span(span, success=True)
                return
            except ToolExecutionError as e:
                self.tracer.end_span(span, success=False, error=str(e))

                # Distinguish retryable (transient) failures from ones that
                # need re-planning — a fixed calculator error retrying
                # won't help; a flaky search timeout retrying often will
                if "not retryable" in str(e):
                    step.status = StepStatus.FAILED
                    self.tracer.log_unrecoverable_failure(session_id, step.step_id, str(e))
                    return

                if attempt == self.MAX_RETRIES:
                    step.status = StepStatus.FAILED
                    self.tracer.log_unrecoverable_failure(
                        session_id, step.step_id, f"Exhausted {self.MAX_RETRIES} retries: {e}"
                    )
                    return

                time.sleep(self.BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))  # exponential backoff
