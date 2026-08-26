# agent-debugging-2026

- **Issue**: "Why did the agent do that?" is the question that matters when production breaks. Agent debugging is 80% observability and 20% inference. You cannot set a breakpoint in production; you have the log. The log is the ground truth.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/categories/patterns/agent-observability-2026.md` and `documentation/categories/patterns/agent-eval-2026.md`.

## Symptom

- A production agent does the wrong thing. You have a trace but the attribute names are framework-specific. You can't see the full prompt, the full response, or the tool-result handling.
- You change the prompt and the agent's behavior changes in a way you cannot predict. There is no replay infrastructure to compare runs.
- A bug report lands, you dig through logs for 4 hours, and you still don't know why. The log format changed by one field name between two versions.
- Two production traces diverge in behavior but look structurally identical. You can't find the difference.

## Root cause

Three things, in order of priority:

1. **No structured trace.** You have ad-hoc logs, not queryable spans.
2. **No deterministic replay.** Every debugging session re-runs the LLM with a different temperature sample. The bug is non-reproducible.
3. **No failure-mode taxonomy.** Triage starts from scratch every time.

The 2026 production pattern: **structured tracing + deterministic replay + eval-as-deploy-gate + a written failure taxonomy**. The first three are infrastructure. The last is discipline.

## The bare minimum structured trace

For every agent run, capture:

- **The exact user input.** Pre-template, pre-mutation. What did the user actually type, send, or upload.
- **The exact prompt sent to the model.** After templating, after RAG injection, after any tool-result injection. Character-for-character, including system prompt and context window contents.
- **The exact model response.** Including reasoning tokens (Claude's extended thinking, GPT-4o "think" steps), structured-output JSON, and any tool-call instructions.
- **Every tool call.** Tool name, arguments (after parsing), validation result, full tool response or error.
- **Timing.** Per-step latency, model TTFT, tool execution time.
- **Token usage.** Per-call input/output tokens. Useful for catching context-window saturation, which is a category of bug in itself.
- **Final state.** What the user actually saw, including any post-processing the agent applied.
- **Session ID, user ID, agent version** on the parent span.

## The OTel GenAI semconv spans (for the agent boundary)

- `invoke_agent {gen_ai.agent.name}` — one reasoning cycle in a multi-step agent
- `chat {gen_ai.request.model}` — single model invocation
- `execute_tool {gen_ai.tool.name}` — agent-initiated tool call
- `mcp.method.name` — MCP server call (OTel v1.39+)
- `gen_ai.usage.input_tokens` / `output_tokens` — per call
- `gen_ai.client.operation.duration` (metric) — latency

See `patterns/agent-observability-2026.md` for the full convention. The point: the trace is **vendor-neutral**, so switching observability backends is a config change, not a re-instrumentation.

## Deterministic replay (the load-bearing piece)

> "Agent debugging is not a log analysis problem. It is a causal reasoning problem that requires structured traces, deterministic replay, and systematic prevention." — zylos research, April 2026

Record every external interaction during a real session (model calls, tool outputs, retrieval results) into a trace file. To debug, **replay the agent against the recorded session by mocking the model and tools with the recorded responses**. The system is now deterministic. You can step through it, change the prompt, change the tool selection logic, change the parser — and re-run with the same inputs.

Two things you can do once you have replay:

- **Counterfactual debugging.** "What if the system prompt had told the agent to never call tool X without verification? Would this bug still have happened?" Modify, replay, check. No live model spend, no waiting.
- **Regression testing.** Save every production bug as a replayable trace. Add it to a regression suite. Re-run every PR against the full suite. Every bug you ever fixed stays fixed.

## The minimum viable replay artifact

`(context_at_turn_N, LLM_response_at_turn_N)` pairs for every turn in the session. Plus the full tool-call I/O. Plus the parsed structured outputs. Plus the timing.

Some teams also store **context fingerprints** — the SHA-256 of the serialized context, plus the list of active instructions, tools, and constraints. When debugging divergent behavior, compare fingerprints at the point of divergence.

## The four-stage debugging workflow

1. **Reconstruct** — load the trace by session ID. Read it start-to-finish before forming any hypothesis.
2. **Isolate** — map the failure to a failure mode. Which of the 8–10 known patterns matches?
3. **Diagnose** — reproduce via replay. Confirm the bug is in the trace, not in the user's report.
4. **Prevent** — convert the diagnosed failure into an eval case. Add to the regression suite before merging the fix.

## The eight (or nine) common agent failure modes

1. **Wrong tool selected** — model called `search_crm` when it should have called `search_kb`.
2. **Wrong tool arguments** — model passed the wrong shape, the wrong entity id, the wrong date range.
3. **Hallucinated tool** — model called a tool that does not exist or is not in the schema.
4. **Context window overflow** — too many tool results crammed in; the model loses the thread.
5. **Infinite loop** — model calls the same tool repeatedly without making progress.
6. **Premature termination** — model returns an answer before fully executing the plan.
7. **Lost in the middle** — the model ignored a critical instruction buried in the middle of the context.
8. **Sycophantic agreement** — the model said "yes" to a user request it should have refused, or agreed to a wrong user assumption.
9. **Drift from persona/system prompt** — the model behaved in a way inconsistent with its instructions.

Track the frequency of each over time. Fix the top three first.

## Side-by-side comparison

The fastest way to find a failure point: load a **successful** trace of the same workflow alongside the failed one. Compare span by span. Identify where they diverge. This works because the agent's intended trajectory is largely deterministic; the divergence is the bug.

## The eval-as-deploy-gate pattern

When a trace fails in production:

1. **Extract the failure case** — input conditions, expected correct behavior, actual incorrect behavior.
2. **Create an eval** — convert into a structured test case: prompt, expected output (or output criteria), and scoring function (exact match, regex, LLM-as-judge, or function check on the final tool call).
3. **Add to CI** — include in the pre-deployment test suite. Future model updates, prompt changes, tool modifications are tested against known failure modes.
4. **Monitor for regression** — some platforms track issue lifecycle (active, resolved, regressed) and automatically reopen issues if a previously fixed failure pattern reappears.

The 2026 production default: **no deploy without eval suite passing**, and the suite must include real production traces, not just synthetic happy-path examples.

## The minimum viable observability stack (2026)

1. **Langfuse** (self-hosted or cloud) for trace capture and debugging UI — 30 minutes to integrate.
2. **Structured logging** with `structlog` or equivalent, correlating `trace_id` in every log line.
3. **Cost accumulation** per session, emitted as a Prometheus gauge.
4. **Session duration** histogram in Prometheus.
5. **Alert** on cost > 5× median and session duration > 2× p95.

Add LangSmith if you're on LangChain/LangGraph. Add Arize Phoenix if you need quality evaluation beyond "did it complete." Add the full OTel pipeline when you have multiple services and need cross-process trace correlation.

## The six things every agent must log

1. The full input prompt.
2. The model response (including reasoning tokens).
3. Every tool call with its arguments and result.
4. Token counts per step.
5. Latency per step.
6. The final outcome of the run.

Tag every trace with `session_id`, `user_id`, and `agent_version`.

## The seven metrics that matter (for any production agent)

1. **Task success rate** — did the agent finish the goal?
2. **Tool call success rate** — what percentage of tool invocations return a non-error response?
3. **Steps per run** — average number of LLM and tool calls per agent invocation. A spike means the agent is looping.
4. **Tokens per run** — directly tied to cost. Watch p95, not just the mean.
5. **Latency per run (p50, p95, p99)** — agents feel slow at the tail.
6. **Cost per resolved task** — divide total spend by successful runs. The only metric that tells you if the agent is economically viable.
7. **Hallucination rate on tool args** — tool calls that fail because the model invented a parameter or a tool that does not exist.

## Gotchas

- **Don't sample traces head-based.** Sample on error type or HTTP status, not on `gen_ai.response.finish_reasons` (which can be missing in streaming failures). Use **tail-based sampling**: 100% of errors, 1–5% of clean runs.
- **The log format changes by one field name between versions.** Use a versioned schema, not a free-form log. JSONL with explicit fields is the minimum.
- **Reasoning tokens are gold.** Claude's extended thinking, GPT-4o "think" steps — log them, even if they cost more. They are the difference between guessing and understanding.
- **Counterfactual inputs are not free.** Replay is replay; you cannot test "what if the user had asked a different question" without a new LLM call.
- **Deterministic replay is not a testing guarantee.** It validates your fix hypothesis against recorded data; it doesn't catch new bugs.
- **The eval suite must include real production traces.** Synthetic happy paths miss real failure modes. Aim for ≥ 30% of the eval set from production.
- **Cluster before you investigate.** When 40 sessions fail, don't investigate 40 sessions. Cluster by failure signature; identify the top 3 patterns; investigate one representative trace per pattern.
- **Don't trust a single trace.** If a bug doesn't reproduce, the replay is incomplete or the divergence is between non-deterministic model calls.
- **The cost of a failed PR merge is the cost of a bad trace in production.** Cheap to build the eval set, expensive to skip.
- **Cross-functional review of agent outputs.** Product, support, and engineering all read traces. The bugs that matter to users are not always the bugs engineers notice first.
- **Tool responses, not just tool calls.** The most common debugging failure is missing the tool's actual response. Always log the full response, or at least its hash + length + a content sample.

## Related

- `documentation/categories/patterns/agent-observability-2026.md` — the OTel GenAI substrate
- `documentation/categories/patterns/agent-eval-2026.md` — the eval-as-deploy-gate pattern
- `documentation/categories/patterns/distributed-tracing-otel.md` — the OTel substrate
- `documentation/categories/lessons/lazy-fail-evidence-discipline.md` — verify before believing
- `documentation/categories/patterns/structured-logging.md` — log shape for events

## Source URLs (verified 2026-08-09)

- "Agent Observability and Production Debugging" (zylos, 2026-04-29) — https://zylos.ai/research/2026-04-29-agent-observability-production-debugging/
- "The AI Agent Debugging Playbook (2026): Traces, Replay, Eval" (jobsbyculture) — https://jobsbyculture.com/blog/ai-agent-debugging-guide-2026
- "Load and Step Through Agent Traces for Debugging" (`agent-replay-trace`) — https://dev.to/mukundakatta/agent-replay-trace-load-and-step-through-agent-traces-for-debugging-4cpf
- "How to Monitor and Debug AI Agents" (zarifautomates) — https://www.zarifautomates.com/blog/how-to-monitor-and-debug-ai-agents
- "Trace-Driven Debugging for AI Agent Failures" (zylos, 2026-04-30) — https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures/
