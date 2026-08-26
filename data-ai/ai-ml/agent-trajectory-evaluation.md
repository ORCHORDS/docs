# agent-trajectory-evaluation

**Issue:** Evaluating only the final answer of an LLM agent misses the real
failure modes — the agent took the wrong tool path, called tools in the wrong
order, wasted 15 steps, or produced a correct answer for the wrong reasons.
**Date:** 2026-08-13
**Status:** documented

## Symptom

The agent's eval scores look acceptable (answer matches the golden answer),
but in production it is slow, expensive, and unreliable. Signals:
- **High token cost per task** even though accuracy is fine — the agent is
  burning steps on exploration that never converges to a better answer.
- **Flaky evals.** The same task passes on one run and fails on the next, and
  the only difference is the number of tool calls or the order.
- **Correct answer, broken path.** The agent got the right answer by luck
  (e.g., a tool returned cached data, or it guessed) rather than by a sound
  sequence of reasoning and tool use.
- **The agent loops.** It calls the same tool 3 times with slightly different
  arguments, or revisits a dead-end step. Output-only eval does not catch this
  because the final answer is still correct.
- **Tool-call errors are invisible.** The agent called a tool with bad
  arguments, got an error, recovered, and still produced a correct answer —
  but the bad call is a latent bug that will fail on a different input.
- **Regression after a prompt change looks fine on accuracy** but the step
  count or tool distribution shifted, indicating a deeper behavior change.

The root cause is that output-only evaluation (does the answer match the
golden?) is necessary but not sufficient for agents, which are multi-step
systems whose quality depends on the trajectory, not just the endpoint.

## Pattern / Solution

### What trajectory evaluation measures

Instead of scoring only `final_answer`, score the full path:

| Metric | What it captures |
|---|---|
| `tool_call_accuracy` | Did the agent call the right tools? |
| `argument_correctness` | Were the tool arguments valid and complete? |
| `step_efficiency` | How many steps vs. the minimum needed? |
| `trajectory_match` | Does the path match the golden trajectory (exact or partial order)? |
| `tool_error_rate` | Fraction of tool calls that errored |
| `recovery_success` | Did the agent recover from an error correctly? |
| `task_completion` | Did the agent actually finish, or hit max steps? |
| `reasoning_quality` | Were intermediate reasoning steps sound (LLM-judge)? |

### Golden trajectory format

Define the expected path as an ordered list of steps, then compare.

```python
golden_trajectory = [
    {"action": "search", "tool": "web_search", "args": {"query": "..."}},
    {"action": "tool", "tool": "fetch_page", "args": {"url": "..."}},
    {"action": "tool", "tool": "extract", "args": {}},
    {"action": "answer"},
]

def trajectory_score(actual, golden):
    """Partial-order match: each golden step must appear in actual in order."""
    idx = 0
    matched = 0
    for step in actual:
        if idx < len(golden) and step_matches(step, golden[idx]):
            matched += 1
            idx += 1
    return matched / len(golden)
```

### LLM-as-judge for trajectory quality

When a golden trajectory is too rigid, use an LLM judge to score the path
on correctness, efficiency, and soundness.

```python
judge_prompt = f"""You are evaluating an AI agent's trajectory for a task.

Task: {task_description}
Expected tools available: {available_tools}
Agent trajectory (steps + tool calls + results):
{format_trajectory(steps)}

Score each dimension 1-5:
1. tool_selection: Did it call the right tools?
2. argument_quality: Were arguments valid and minimal?
3. efficiency: Were steps necessary, or redundant/looping?
4. error_handling: Did it recover from errors sensibly?
5. reasoning_soundness: Did intermediate reasoning support the conclusion?

Return JSON: {{tool_selection: int, argument_quality: int, ...,
overall: float, explanation: str}}
"""
scores = llm_judge.generate(judge_prompt, temperature=0.0)
```

### Offline vs. online trajectory eval

- **Offline (CI / eval set):** Run N tasks with known golden trajectories,
  assert trajectory_match >= threshold and step_count <= max_steps.
- **Online (production traces):** Sample X% of real traces, run the LLM judge
  asynchronously, and alert on drops in efficiency or tool accuracy.

```python
# CI gate: block deploy if trajectory quality regresses
def ci_eval():
    results = [run_agent(case) for case in eval_set]
    mean_traj = mean(r.trajectory_match for r in results)
    mean_steps = mean(len(r.steps) for r in results)
    assert mean_traj >= 0.85, f"trajectory match dropped to {mean_traj}"
    assert mean_steps <= 8, f"agent too verbose: {mean_steps} steps avg"
```

### Capturing the trajectory

You cannot evaluate what you do not record. Instrument every step.

```python
@dataclass
class AgentStep:
    thought: str
    tool: str
    args: dict
    result: Any
    error: str | None
    latency_ms: int
    tokens_used: int

trace: list[AgentStep] = []

def run_agent(task):
    while not done:
        step = plan_and_act()
        trace.append(step)
    return AgentRun(task=task, steps=trace, final_answer=answer)
```

Persist full traces (not just the answer) to your eval store so you can
re-score them when the judge prompt or golden trajectories change.

## Gotchas

- **Golden trajectories are brittle.** Insisting on an exact path kills
  legitimate alternative solutions. Use partial-order match or LLM-judge
  instead of exact step equality.
- **Trajectory eval is expensive.** LLM-as-judge on every step multiplies
  cost. Sample in production (e.g., 1-5% of traces), run full eval offline
  only on the eval set.
- **Step count is not efficiency.** An agent that takes 3 good steps is
  better than one that takes 1 step with a bloated prompt. Measure steps
  AND tokens AND tool calls together.
- **Recovery can mask bugs.** A high recovery_success score is good, but a
  rising tool_error_rate is a red flag — the agent is making more mistakes
  and just covering them up. Track both.
- **Eval set drift.** If the eval set only covers happy paths, trajectory
  metrics will look great and the agent will fail on edge cases in prod.
  Include error-injection cases (force a tool to fail) to test recovery.
- **Judge bias.** The LLM judge may prefer verbose trajectories or rate its
  own reasoning style highly. Calibrate against human labels on a small set
  and check for correlation.
- **Non-determinism breaks comparisons.** Run each eval case multiple times
  (temperature=0 if possible) and aggregate. A single run tells you nothing
  about an agent's variance.
- **Trajectory eval does not replace output eval.** Use both. A perfect
  trajectory with a wrong final answer is still a failure.

## Related
- `agent-evaluation-patterns.md` — broader agent eval methodology
- `llm-as-judge-trace-evaluation.md` — LLM-judge for trace scoring
- `agent-observability-tracing.md` — capturing the traces to evaluate
- `agent-error-recovery.md` — testing recovery behavior specifically
- `agent-planning-react.md` — the loop being evaluated
- `prompt-testing-evals.md` — pinning parameters for reproducible eval runs
