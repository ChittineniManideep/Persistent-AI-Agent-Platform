"""
Tests for the agent orchestration layer — proving the plan/execute/
checkpoint/resume cycle actually works, including the retry and
unrecoverable-failure paths, not just the happy path.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.planner import plan_goal, StepStatus
from agent.executor import AgentExecutor
from agent.session_store import SessionStore, rehydrate_plan
from observability.tracing import AgentTracer


def test_full_plan_completes():
    plan = plan_goal("research and summarize recent AI agent frameworks")
    store = SessionStore(redis_url=None)
    tracer = AgentTracer()
    executor = AgentExecutor(store, tracer)

    result = executor.run(plan, session_id="test-session-1")
    assert result.is_complete(), "Plan should complete all steps"
    assert all(s.status == StepStatus.COMPLETE for s in result.steps)
    print("test_full_plan_completes: PASS")


def test_checkpoint_and_resume():
    """The core 'persistent across sessions' requirement: save state,
    reload it fresh (as if from a restart), and continue from there."""
    plan = plan_goal("research and summarize recent AI agent frameworks")
    store = SessionStore(redis_url=None)
    session_id = "test-session-2"
    store.save_plan(session_id, plan)

    # Simulate a restart: load raw JSON back and rehydrate, not reusing
    # the in-memory Python object
    raw = store.load_plan_raw(session_id)
    rehydrated = rehydrate_plan(raw)
    assert rehydrated.goal == plan.goal
    assert len(rehydrated.steps) == len(plan.steps)
    assert all(s.status == StepStatus.PENDING for s in rehydrated.steps)

    tracer = AgentTracer()
    executor = AgentExecutor(store, tracer)
    completed = executor.run(rehydrated, session_id)
    assert completed.is_complete()
    print("test_checkpoint_and_resume: PASS")


def test_unrecoverable_failure_halts_plan():
    plan = plan_goal("calculate divide by zero result")
    store = SessionStore(redis_url=None)
    tracer = AgentTracer()
    executor = AgentExecutor(store, tracer)

    result = executor.run(plan, session_id="test-session-3")
    assert result.has_unrecoverable_failure()
    assert not result.is_complete()
    assert tracer.summary()["unrecoverable_failures"] >= 1
    print("test_unrecoverable_failure_halts_plan: PASS")


def test_retry_recovers_from_transient_failure():
    """Runs many trials since web_search fails randomly ~15% of the time —
    confirms the retry path actually recovers most of those, rather than
    only working when nothing goes wrong."""
    successes = 0
    trials = 30
    for i in range(trials):
        plan = plan_goal("research and summarize agent frameworks")
        store = SessionStore(redis_url=None)
        tracer = AgentTracer()
        executor = AgentExecutor(store, tracer)
        result = executor.run(plan, session_id=f"retry-test-{i}")
        if result.is_complete():
            successes += 1

    print(f"test_retry_recovers_from_transient_failure: {successes}/{trials} completed "
          f"despite ~15% per-call tool flakiness")
    assert successes >= trials * 0.9, "Retry logic should recover from most transient failures"
    print("test_retry_recovers_from_transient_failure: PASS")


if __name__ == "__main__":
    test_full_plan_completes()
    test_checkpoint_and_resume()
    test_unrecoverable_failure_halts_plan()
    test_retry_recovers_from_transient_failure()
    print("\nAll agent orchestration tests passed.")
