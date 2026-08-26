# agent-reflection-patterns

**Issue:** Implementing self-critique and reflection loops in agents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Agents produce suboptimal first drafts; reflection improves quality on complex tasks.

## Pattern / Solution
```python
async def reflect_and_revise(task: str, initial_output: str, criteria: str) -> str:
    critique_prompt = f"""Review this output for the task: {task}

Output: {initial_output}

Evaluate against: {criteria}
Provide specific, actionable critique. Be concise."""

    critique = await llm(critique_prompt)

    revise_prompt = f"""Revise the output based on this critique:
Original: {initial_output}
Critique: {critique}
Revised output:"""

    return await llm(revise_prompt)

# Iterative refinement
for _ in range(3):
    output = await reflect_and_revise(task, output, criteria)
```

## Gotchas
- Reflection loops can over-optimize and lose valid content — cap at 2-3 iterations
- Use separate LLM calls for critique and revision to avoid self-serving bias
- Log each iteration for debugging quality regressions

## Related
- `agent-planning-react.md`
- `agent-evaluation-patterns.md`
