# llm-function-calling

**Issue:** Using LLM function calling to trigger application logic
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Models need to call external APIs or execute code based on user intent.

## Pattern / Solution
```python
tools = [{
    "type": "function",
    "function": {
        "name": "search_database",
        "description": "Search product database by query",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
    },
}]

response = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
if response.choices[0].message.tool_calls:
    call = response.choices[0].message.tool_calls[0]
    result = dispatch(call.function.name, json.loads(call.function.arguments))
```

## Gotchas
- Always validate tool arguments before executing — models hallucinate params
- Return tool results as a `tool` role message with matching `tool_call_id`
- Parallel tool calls are possible; handle the list, not just index 0

## Related
- `llm-tool-use-patterns.md`
- `agent-tool-design.md`
