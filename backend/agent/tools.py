"""
Tool implementations the agent can invoke. Kept intentionally simple/mocked
where a real external dependency would sit (web search, external APIs) —
the point of this project is the agent orchestration layer, not building
production search infrastructure.
"""
import random
import time


class ToolExecutionError(Exception):
    """Raised when a tool fails — the executor catches this specifically
    to distinguish a retryable tool failure from an unexpected exception."""
    pass


def web_search(query: str, **kwargs) -> dict:
    # Simulated flaky external dependency — fails ~15% of the time, the
    # kind of real-world tool unreliability the executor's retry logic
    # exists to handle
    if random.random() < 0.15:
        raise ToolExecutionError(f"web_search timed out for query: {query}")
    return {"results": [f"Result {i} for '{query}'" for i in range(1, 6)]}


def rerank(step_context: dict, **kwargs) -> dict:
    # In the real system this calls ml/reranker_model.py — mocked here at
    # the orchestration-layer test boundary so agent tests don't depend on
    # loading the actual PyTorch model
    prior_results = step_context.get("s1", {}).get("results", [])
    return {"reranked_results": list(reversed(prior_results))[:3]}


def extract_facts(step_context: dict, **kwargs) -> dict:
    reranked = step_context.get("s2", {}).get("reranked_results", [])
    return {"facts": [f"Fact extracted from: {r}" for r in reranked]}


def summarize(step_context: dict, **kwargs) -> dict:
    facts = step_context.get("s3", {}).get("facts") or step_context.get("s1", {}).get("results", [])
    return {"summary": f"Summary of {len(facts)} inputs: " + "; ".join(str(f) for f in facts[:3])}


def parse_expression(query: str, **kwargs) -> dict:
    return {"parsed_expression": query}


def calculator(step_context: dict, **kwargs) -> dict:
    # Deliberately fails on a specific pattern to demonstrate an
    # UNrecoverable failure path (vs. web_search's recoverable flakiness)
    expr = step_context.get("s1", {}).get("parsed_expression", "")
    if "divide by zero" in expr.lower():
        raise ToolExecutionError("Division by zero — not retryable, requires re-planning")
    return {"result": "42 (simulated)"}


def structured_lookup(query: str, **kwargs) -> dict:
    return {"lookup_result": f"Structured data for: {query}"}


TOOL_REGISTRY = {
    "web_search": web_search,
    "rerank": rerank,
    "extract_facts": extract_facts,
    "summarize": summarize,
    "parse_expression": parse_expression,
    "calculator": calculator,
    "structured_lookup": structured_lookup,
}
