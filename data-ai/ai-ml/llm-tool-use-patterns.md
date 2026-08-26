# llm-tool-use-patterns

**Issue:** Designing and executing tools for LLM agents reliably
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poorly designed tools cause agents to misuse them or fail silently.

## Pattern / Solution
```python
# Anthropic tool use
tools = [{
    "name": "run_sql",
    "description": "Execute a read-only SQL query and return results as JSON",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "SQL SELECT statement"}},
        "required": ["query"],
    },
}]

# Handle tool use response
for block in response.content:
    if block.type == "tool_use":
        result = execute_tool(block.name, block.input)
        messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": block.id, "content": str(result)}]})
```

## Gotchas
- Keep tool descriptions precise and include example inputs/outputs
- Return error strings in tool_result, not exceptions — let model handle gracefully
- Limit tool count per call to <10 for best model performance

## Related
- `llm-function-calling.md`
- `agent-tool-design.md`
