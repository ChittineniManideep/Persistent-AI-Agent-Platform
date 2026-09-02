"""
Agent planner — decomposes a user goal into an ordered sequence of steps,
each with a tool assignment. This is the "planning" half of multi-step
agent workflow engineering: the agent doesn't just call one tool and
respond, it builds a plan it can checkpoint, resume, and partially
re-plan if a step fails.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class PlanStep:
    step_id: str
    description: str
    tool_name: str
    tool_input: dict
    status: StepStatus = StepStatus.PENDING
    result: Optional[dict] = None
    attempt_count: int = 0
    depends_on: list = field(default_factory=list)  # step_ids that must complete first


@dataclass
class Plan:
    plan_id: str
    goal: str
    steps: list[PlanStep]

    def next_runnable_step(self) -> Optional[PlanStep]:
        """Returns the next PENDING step whose dependencies are all COMPLETE —
        this is what makes the plan resumable: after a restart, this function
        picks up exactly where execution left off, using persisted step status
        rather than re-running the whole plan from step 1."""
        completed_ids = {s.step_id for s in self.steps if s.status == StepStatus.COMPLETE}
        for step in self.steps:
            if step.status == StepStatus.PENDING and set(step.depends_on).issubset(completed_ids):
                return step
        return None

    def is_complete(self) -> bool:
        return all(s.status == StepStatus.COMPLETE for s in self.steps)

    def has_unrecoverable_failure(self) -> bool:
        return any(s.status == StepStatus.FAILED for s in self.steps)


# Simple rule-based planner for the demo scope — in a production system this
# step would call an LLM (e.g. via LangChain) to decompose an arbitrary goal;
# the rule-based version here keeps the plan structure fully deterministic
# and testable, which matters for demonstrating the state machine correctly
# rather than depending on LLM output variability for the demo.
def plan_goal(goal: str) -> Plan:
    plan_id = str(uuid.uuid4())[:8]

    if "research" in goal.lower() and "summarize" in goal.lower():
        steps = [
            PlanStep("s1", "Search for relevant sources", "web_search", {"query": goal}),
            PlanStep("s2", "Rerank search results for relevance", "rerank", {}, depends_on=["s1"]),
            PlanStep("s3", "Extract key facts from top results", "extract_facts", {}, depends_on=["s2"]),
            PlanStep("s4", "Summarize findings", "summarize", {}, depends_on=["s3"]),
        ]
    elif "calculate" in goal.lower() or "compute" in goal.lower():
        steps = [
            PlanStep("s1", "Parse the calculation request", "parse_expression", {"query": goal}),
            PlanStep("s2", "Execute calculation", "calculator", {}, depends_on=["s1"]),
        ]
    else:
        steps = [
            PlanStep("s1", "Look up relevant information", "structured_lookup", {"query": goal}),
            PlanStep("s2", "Formulate response", "summarize", {}, depends_on=["s1"]),
        ]

    return Plan(plan_id=plan_id, goal=goal, steps=steps)
