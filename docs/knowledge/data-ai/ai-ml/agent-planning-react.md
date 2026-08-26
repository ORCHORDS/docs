# agent-planning-react

**Issue:** Implementing the ReAct (Reason+Act) planning pattern for agents
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Agents need to interleave reasoning and action to solve multi-step tasks.

## Pattern / Solution
```python
REACT_SYSTEM = """You solve tasks by thinking step by step.
Format your response as:
Thought: [reasoning about what to do next]
Action: tool_name
Action Input: {"param": "value"}

When you have the final answer:
Thought: I now know the answer
Final Answer: [answer]"""

async def react_loop(task: str, tools: dict, max_steps: int = 10):
    messages = [{"role": "user", "content": task}]
    for _ in range(max_steps):
        response = await llm(messages, system=REACT_SYSTEM)
        if "Final Answer:" in response:
            return extract_final_answer(response)
        tool_name, tool_input = parse_action(response)
        result = await toolstool_name
        messages.extend([{"role": "assistant", "content": response},
                         {"role": "user", "content": f"Observation: {result}"}])
    raise TimeoutError("Max steps reached")
```

## Gotchas
- ReAct is sensitive to prompt format — test exact whitespace/colon patterns
- Use structured output (tool_use API) instead of text parsing for reliability
- Limit observations to 500 tokens to avoid context bloat

## Related
- `agent-architecture-patterns.md`
- `agent-error-recovery.md`
