"""
Session store — persists plan state so a session survives process restart,
client disconnect, or a redeploy mid-execution. Redis is the real target
(pattern shown below); an in-memory fallback is included so this module
runs standalone in tests/demo without a live Redis instance, while the
interface is identical either way — swapping the backend doesn't change
any calling code in executor.py.
"""
import json
import dataclasses
from typing import Optional

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class SessionStore:
    def __init__(self, redis_url: Optional[str] = None):
        self.use_redis = REDIS_AVAILABLE and redis_url is not None
        if self.use_redis:
            self.client = redis.from_url(redis_url)
        else:
            self._memory_store = {}

    def save_plan(self, session_id: str, plan) -> None:
        payload = json.dumps(dataclasses.asdict(plan), default=str)
        if self.use_redis:
            # TTL matters here: a session shouldn't persist forever — 24h
            # covers "user closed the tab and came back later today"
            # without accumulating stale state indefinitely
            self.client.set(f"agent_session:{session_id}", payload, ex=86400)
        else:
            self._memory_store[session_id] = payload

    def load_plan_raw(self, session_id: str) -> Optional[dict]:
        if self.use_redis:
            raw = self.client.get(f"agent_session:{session_id}")
        else:
            raw = self._memory_store.get(session_id)
        return json.loads(raw) if raw else None

    def delete_session(self, session_id: str) -> None:
        if self.use_redis:
            self.client.delete(f"agent_session:{session_id}")
        else:
            self._memory_store.pop(session_id, None)


def rehydrate_plan(raw: dict):
    """Reconstructs a Plan/PlanStep dataclass tree from the JSON persisted
    by save_plan — this is what makes resume-after-restart actually work,
    not just theoretically possible."""
    from .planner import Plan, PlanStep, StepStatus
    steps = [
        PlanStep(
            step_id=s["step_id"], description=s["description"], tool_name=s["tool_name"],
            tool_input=s["tool_input"], status=StepStatus(s["status"]), result=s["result"],
            attempt_count=s["attempt_count"], depends_on=s["depends_on"],
        )
        for s in raw["steps"]
    ]
    return Plan(plan_id=raw["plan_id"], goal=raw["goal"], steps=steps)
