# langgraph-patterns

**Issue:** Building stateful agent workflows with LangGraph
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Complex agent flows with conditionals, loops, and human-in-the-loop need explicit state management.

## Pattern / Solution
```python
from langgraph.graph import StateGraph, END
from typing import TypedDict

class AgentState(TypedDict):
    messages: list
    task: str
    result: str | None

builder = StateGraph(AgentState)

builder.add_node("planner", planner_node)
builder.add_node("executor", executor_node)
builder.add_node("reviewer", reviewer_node)

builder.set_entry_point("planner")
builder.add_edge("planner", "executor")
builder.add_conditional_edges("reviewer", lambda s: "executor" if s["needs_revision"] else END)

graph = builder.compile(checkpointer=MemorySaver())
result = await graph.ainvoke({"task": "analyze sales data"}, config={"configurable": {"thread_id": "1"}})
```

## Gotchas
- Checkpointers enable resume after failures — use SqliteSaver for persistence
- State schema must be defined upfront; changes require migration
- Human interrupts use `interrupt_before=["executor"]` in compile()

## Related
- `agent-multi-agent-orchestration.md`
- `agent-human-in-the-loop.md`
