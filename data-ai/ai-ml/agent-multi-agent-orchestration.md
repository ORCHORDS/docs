# agent-multi-agent-orchestration

**Issue:** Orchestrating multiple specialized agents to solve complex tasks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single agents become brittle on complex tasks that require diverse expertise.

## Pattern / Solution
```python
class Orchestrator:
    def __init__(self):
        self.agents = {
            "researcher": ResearchAgent(),
            "coder": CodingAgent(),
            "reviewer": ReviewAgent(),
        }

    async def run(self, task: str) -> str:
        plan = await self.plan(task)
        results = {}
        for step in plan:
            agent = self.agents[step["agent"]]
            context = {k: results[k] for k in step.get("depends_on", [])}
            results[step["id"]] = await agent.run(step["task"], context=context)
        return results[plan[-1]["id"]]
```
Use LangGraph or CrewAI for production multi-agent systems.

## Gotchas
- Shared state between agents causes race conditions in parallel execution
- Always pass structured context, not raw conversation history between agents
- Define clear agent contracts (inputs/outputs) before implementation

## Related
- `agent-architecture-patterns.md`
- `langgraph-patterns.md`
