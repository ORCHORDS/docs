# agent-observability-tracing

**Issue:** Adding observability and distributed tracing to agent pipelines
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Agent failures are hard to debug without visibility into tool calls, LLM inputs/outputs, and timing.

## Pattern / Solution
```python
from langfuse import Langfuse
from opentelemetry import trace

langfuse = Langfuse()

async def traced_agent_run(task: str) -> str:
    trace = langfuse.trace(name="agent-run", input={"task": task})

    span = trace.span(name="llm-call")
    response = await llm(messages)
    span.end(output={"response": response, "tokens": usage})

    span = trace.span(name="tool-call", input={"tool": tool_name, "args": args})
    result = await tool_fn(args)
    span.end(output={"result": result})

    trace.update(output={"final": result})
    return result
```

## Gotchas
- Use Langfuse or Arize Phoenix for LLM-specific tracing; standard OTEL lacks LLM semantics
- Always log prompt + completion together for cost attribution
- Mask PII in traces before storing

## Related
- `agent-evaluation-patterns.md`
- `ai-cost-monitoring.md`
