# llm-as-judge-trace-evaluation

> Using an LLM (or a full agent) to score, rank, or classify the outputs and
> execution trajectories of other LLM agents. The dominant 2026 evaluation
> pattern for agentic systems where traditional unit-test assertions cannot
> capture "was this a good response."

## Symptom

You shipped an agent and now need to know if it's actually good. You hit:

- Human review does not scale — you have 500 traces/day, reviewers can read 20.
- Classic assertions (`assert "Paris" in output`) pass on outputs a human would
  reject as evasive, incomplete, or confidently wrong.
- The agent's final answer looks fine, but it called the wrong tool, looped 4
  times, and burned 8x the tokens it should have. Output-only evals miss this.
- You changed the system prompt and "tests pass," but quality clearly regressed
  in production. You have no regression signal.
- Two judge models disagree on every sample, so you cannot trust either.

Root cause: agentic quality is multi-dimensional (task success + tool-call
correctness + efficiency + safety), lives across an entire *trajectory* not just
the final message, and requires a scalable automated judge calibrated against
human labels.

## Two evaluation modes: output vs trajectory

- **Output evaluation** — score only the final answer. Cheap, good for chat/QA.
  Blind to how the agent got there.
- **Trajectory / trace evaluation** — score the full execution path: every
  reasoning step, every tool call (right tool? right args? right order?),
  recovery from errors, and the final result. Required for agents.

For agents, trajectory is the primary mode; output is a sanity check on top.

## LLM-as-a-Judge techniques

1. **Scoring (pointwise)** — judge gives a 1-5 score per rubric dimension.
   Fast, but scores drift between runs and models.
2. **Pairwise comparison** — judge sees two outputs A and B and picks the
   winner. More stable than absolute scoring, but O(n^2) over a candidate set.
3. **Rubric-based grading** — give the judge an explicit rubric (e.g., "1 = refuses,
   3 = partial, 5 = fully correct and concise") with anchor examples. Reduces
   drift dramatically. Always prefer this over free-form scoring.

```python
import json

JUDGE_PROMPT = """You are grading an AI agent's response.
Rubric:
  1 = wrong or refuses
  3 = partially correct
  5 = fully correct and concise

User query: {query}
Agent response: {response}

Return JSON: {{"score": int, "reason": str}}"""

def judge_one(query: str, response: str, judge_model) -> dict:
    out = judge_model.complete(JUDGE_PROMPT.format(query=query, response=response))
    return json.loads(out)  # {"score": 4, "reason": "..."}
```

## Trace-based evaluation pattern

Capture a structured trace per run, then score each meaningful step.

```python
# A trace is an ordered list of events
trace = [
    {"type": "plan",      "content": "..."},
    {"type": "tool_call", "name": "search",   "args": {...}, "ok": True},
    {"type": "tool_call", "name": "read_file","args": {...}, "ok": True},
    {"type": "tool_call", "name": "delete",   "args": {...}, "ok": False,
     "error": "permission denied"},
    {"type": "answer",    "content": "..."},
]

TRAJECTORY_JUDGE = """Grade this agent trajectory.
Check: (a) were the tool calls correct and in a sensible order?
(b) did it recover well from the error? (c) is the final answer correct?
Query: {query}
Trace: {trace}
Return JSON: {{"tool_correctness": 1-5, "recovery": 1-5,
             "final_answer": 1-5, "notes": str}}"""
```

Key dimensions to score across:
- **Tool correctness** — right tool, right args, right order.
- **Task completion** — did it actually solve the user's problem?
- **Reasoning quality** — was the plan sensible, not circular?
- **Efficiency** — tool calls vs minimum needed (over-calling = cost + latency).
- **Safety** — did it stay in scope, refuse harmful actions?

## Judge calibration (mandatory)

A raw LLM judge is not trustworthy until calibrated against humans.

1. Build a **golden set**: 50-200 examples a human has labeled with the same
   rubric.
2. Run the judge on the golden set.
3. Compute agreement: Cohen's kappa or Pearson correlation vs human labels.
4. Target kappa >= 0.6 before trusting the judge for regression gating.
5. If agreement is low, improve the rubric (more anchors) or switch judge model.
   Do not just re-run and hope.

## Agent-as-a-Judge

2026 extension: instead of a single LLM call, the judge is itself an agent that
can run tools, re-execute sub-steps, and check intermediate state. More accurate
on complex tasks, much slower and more expensive. Reserve for high-stakes
evaluation (evals gating a deploy, not routine CI).

## CI regression gating

```yaml
# .github/workflows/agent-eval.yml
- name: Run agent eval suite
  run: pnpm eval --suite golden-200 --judge claude-sonnet --threshold 0.85
- name: Fail on regression
  run: pnpm eval-gate --min-pass-rate 0.85 --max-regression 0.03
```

Gate on pass-rate and on max allowed regression vs the previous commit. A 3%
drop should block merge even if absolute pass rate is still high — that's the
early warning.

## Gotchas

- **Position bias.** In pairwise comparison, judges prefer whichever output is
  shown first. Always swap A/B order and average, or you'll ship the wrong model.
- **Verbosity bias.** Judges (and humans) rate longer answers higher even when
  the short one is correct. Add "conciseness" to the rubric and penalize padding.
- **Self-preference.** A Claude judge rates Claude outputs higher; GPT rates GPT
  higher. Use a different model family for the judge than for the system under
  test, or rotate judges.
- **Schema compliance != semantic correctness.** If the judge only checks "did it
  return valid JSON matching the schema," it will pass confidently-wrong answers.
  The judge must reason about content, not just format.
- **Judge cost is real.** Scoring 200 traces with a frontier judge at $0.01-0.05
  each is cheap per run, but in CI on every PR it adds up. Cache judge results
  keyed by (trace hash + judge model + rubric version).
- **Golden set rot.** Your golden set reflects the product as it was when labeled.
  When capabilities change, old "5 = perfect" examples may now be trivially
  improvable. Re-label quarterly.
- **Trace length blows up judge tokens.** A 15-step trace with full tool outputs
  can be 20k+ tokens per judge call. Summarize tool outputs in the trace before
  sending to the judge; keep raw outputs in cold storage for spot audits.
- **Single-number scores hide regressions.** A composite "quality: 4.2" can stay
  flat while one dimension (e.g., safety) collapses and others rise. Always score
  per-dimension and track each independently.
- **Don't optimize for the judge.** If you tune prompts to maximize the judge
  score, you are overfitting to the judge's biases, not improving real quality.
  Periodically re-validate against fresh human labels on *new* examples.
