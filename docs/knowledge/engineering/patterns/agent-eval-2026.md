# agent-eval-2026

- **Issue**: An agent is not a single LLM call. "Did the answer look right" is necessary and insufficient. You need to score trajectory, tool use, task completion, and multi-turn quality, with the right mix of deterministic code, LLM-as-judge, and human labels.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; supplements `documentation/docs/policies/lessons/agent-iteration-discipline.md` and the existing `documentation/docs/policies/patterns/e2e-testing-patterns.md`.

## Symptom

- You ship an "agent eval" that only checks the final message. The agent gives the right answer via the wrong path (extra tool calls, retries, an unexpected side effect). Your eval says pass; production says incident.
- Your eval suite passes 100%. The agent loops in production. You had no loop detector.
- You add LLM-as-judge but it disagrees with humans more than expected. You never calibrated.
- Two teams pick two different eval platforms, can't compare results.

## Root cause

The unit of evaluation for an agent is a **trace or session**, not a single input-output pair. The 2026 framework landscape (LangSmith, Braintrust, Langfuse, DeepEval, Arize Phoenix, Galileo, Inspect AI, OpenAI Evals, Latitude) splits into **frameworks** (point at your own agent) and **platforms** (managed observability + eval + human review). Picking wrong on either axis is expensive.

## The four dimensions of agent quality

| Dimension | Question | Typical metrics |
|---|---|---|
| **Trajectory** | Did the agent take a sensible path? | Step count, unnecessary tool calls, loops/retries, required steps present, correct ordering, trajectory match |
| **Tool use** | Did it call the right tools correctly? | Correct tool selected, argument validity, tool error rate, recovery after failed calls |
| **Task completion** | Did the user get what they asked for? | Goal achievement, answer correctness, resolution rate |
| **Multi-turn quality** | Does quality hold across a conversation? | Context retention, goal drift, turns-to-resolution, session-level outcome |

**Start with one metric per dimension.** A boolean task-completion judgment on the root of each run, a tool-selection correctness check on tool-call observations, a step count with a budget threshold for trajectory efficiency, a session-level resolution score for conversational agents.

## The three evaluator types

| Type | Use for | Cost / latency | Examples |
|---|---|---|---|
| **Code evaluators** | Deterministic, objective checks | Free per run, ms | Required tool was called, args parse against schema, step budget respected, output is valid JSON |
| **LLM-as-a-judge** | Semantic judgment at scale | Model cost per evaluation, seconds | Task completion without ground truth, reasoning quality, groundedness |
| **Human annotation** | Ground truth and calibration | Expert time | Labeling ambiguous trajectories, building the reference set judges are calibrated against |

The 2026 production pattern: **code evaluators everywhere it's decidable, LLM-as-judge for the rest, human labels to calibrate the judges.** Run **offline** (against a fixed dataset before ship) and **online** (against sampled production traffic after ship).

## Framework vs platform (2026 matrix)

| Platform | Orientation | Self-host | Offline eval | Online eval on prod | Trajectory eval | Starting price |
|---|---|---|---|---|---|---|
| Arize AX | Production observability + eval | Managed / enterprise self-hosted | Yes | Yes | Yes | Usage-based |
| Arize Phoenix | OSS tracing + eval | Self-host or local | Yes | Limited | Yes | Free (Apache 2.0) |
| LangSmith | LangChain/LangGraph tracing + eval | Managed / self-host on higher tiers | Yes | Yes | Yes | Free tier; $39/seat/mo |
| Braintrust | Pre-release experimentation | Managed / self-host enterprise | Yes | Partial | Partial | Free tier; $249/mo flat |
| Langfuse | OSS LLM tracing | Self-host or cloud (MIT) | Yes | Partial | Partial | Free self-host; $29/mo cloud |
| W&B Weave | Eval inside W&B | Managed | Yes | Partial | Partial | Included with W&B |
| Comet Opik | OSS agent evaluation | Self-host or managed | Yes | Partial | Partial | Free self-host |
| Galileo | Regulated enterprise | VPC + on-prem | Yes | Yes | Yes | Contact |
| Inspect AI | UK AISI safety eval | Self-host (MIT) | Yes | No | Yes | Free |
| OpenAI Evals | Registry-based benchmarks | Self-host (MIT) | Yes | No | Limited | Free + API costs |
| Latitude | Agent-native, MCP-driven | Self-host (MIT) | Yes | Yes | Yes | Free; $99/mo Pro |

**Rule of thumb** (May 2026):
- Solo builders → DeepEval (Apache 2.0, 50+ metrics) + Arize Phoenix (free, self-hostable trace UI) covers 80% of pre-prod eval at zero cost.
- 5-person product teams → Braintrust on flat pricing ($249/mo unlimited users) for CI gates and serious evals.
- LangChain shops → LangSmith Plus ($39/seat/mo) only if you are deep on LangGraph.
- Regulated enterprises → Galileo, Confident AI self-hosted, or UK AISI Inspect AI.
- Production multi-turn agents → Latitude for the issue → PR loop via MCP.

## Patterns

### Run a code evaluator on every tool call

```ts
const stepCount = trace.spans.length;
const loopDetected = detectLoop(trace, { windowSize: 4 });
const requiredToolCalled = trace.spans.some(s => s.name === "search_docs");
expect(stepCount).toBeLessThan(20);
expect(loopDetected).toBe(false);
expect(requiredToolCalled).toBe(true);
```

### LLM-as-judge for groundedness

```py
judge = {
  "model": "claude-sonnet-5",
  "prompt": "Is the answer grounded in the retrieved context? Reply PASS or FAIL with one sentence.",
  "input": {"answer": final_answer, "context": retrieved_chunks},
  "output_schema": {"verdict": "PASS|FAIL", "reason": "str"},
}
```

### Calibrate the judge against humans

1. Have 2-3 domain experts label 100 representative trajectories.
2. Run your LLM judge on the same 100.
3. Compute Cohen's kappa. Target ≥ 0.7.
4. Below 0.7: refine the prompt, add few-shot examples, or escalate to a bigger judge model.

### Online eval with sampling

```ts
if (Math.random() < 0.05) {                    // 5% sample
  await platform.recordEvaluation({
    trace_id: trace.id,
    evaluators: ["task_completion", "tool_correctness", "step_budget"],
  });
}
```

## Verification

- **Per-dimension baseline** — measure the four dimensions on a known set before changing anything. You can't tell if a change helped without a baseline.
- **Calibrated judge agreement** — Cohen's kappa ≥ 0.7 with humans. Below 0.5, your judge is not useful.
- **Inter-platform reproducibility** — if you switch platforms, run the same dataset through both and compare. A 5pp delta is noise; a 20pp delta is a methodology problem.
- **Online vs offline parity** — pick the same eval set, run offline, run on 1% of prod, compare. They should agree within noise.

## Gotchas

- **Trajectory match is not the same as task completion.** Right answer via the wrong path is still a fail. Both metrics are needed.
- **LLM-as-judge without calibration is theatre.** Measure agreement with humans before trusting the score.
- **Final-answer-only evals under-detect failure modes.** Tool mis-use, looping, and side effects all show up in trajectory, not in the final message.
- **"Self-hosted" means full feature parity, not a stripped-down OSS version.** Confirm before you commit to a 6-month migration.
- **Online eval sampling rate matters.** 1% undercounts rare failures; 10% blows up cost. 5% with stratified sampling is a reasonable default.
- **Step budget is per-agent, not global.** A research agent that needs 30 steps is fine; a customer-support agent that needs 30 steps is broken. Set per-agent.
- **Loop detection is a code evaluator, not a judge.** It runs on every trace, in milliseconds, and gates the run before the LLM judge is even called.
- **Don't eval on synthetic prompts only.** Real prod traffic is messier; eval at least 30% on real traces (anonymized).

## Related

- `documentation/docs/policies/patterns/e2e-testing-patterns.md` — pre-prod tests vs online evals
- `documentation/docs/policies/patterns/observability-three-pillars.md` — metrics/logs/traces as the substrate
- `documentation/docs/policies/patterns/distributed-tracing-otel.md` — OpenTelemetry-based tracing that all of these platforms ingest
- `documentation/docs/policies/lessons/agent-iteration-discipline.md` — when to stop iterating
- `documentation/docs/policies/patterns/agent-cost-optimization.md` — eval cost is part of total agent cost

## Source URLs (verified 2026-08-09)

- "LLM & agent evaluation platforms: 2026 comparison" (Arize) — https://arize.com/resources/llm-and-agent-evaluation-platforms/
- "8 AI Agent Evaluation Frameworks: A Hands-On Comparison" — https://growthengineer.ai/blog/ai-agent-evaluation-frameworks-compared
- "Best AI Evaluation Tools for Agents in 2026" (Latitude) — https://latitude.so/blog/agent-first-comparison-guide-vs-braintrust
- Langfuse: "AI agent evaluation: trajectory, tool calls, and task completion" — https://langfuse.com/resources/engineering/ai-agent-evaluation
- Morph: "AI Agent Evaluation (2026): Metrics, Frameworks" — https://www.morphllm.com/ai-agent-evaluation
- Phoenix (Arize OSS) — https://github.com/Arize-ai/phoenix
- DeepEval — https://github.com/confident-ai/deepeval
- Inspect AI (UK AISI) — https://github.com/UKGovernmentBEIS/inspect_ai
