# agent-self-correction

- **Issue**: An agent produces a wrong answer and does not catch it. Adding a self-critique step sometimes helps, sometimes loops, sometimes makes it worse.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2 (research, no human approval needed per project rule)
- **Status**: Active lesson; this entry supersedes the ad-hoc rule "always ask the model to double-check."

## Symptom

You wire up a reflection loop. The agent now produces a "second pass" answer. Two failure modes appear in production:

1. **Loop-of-futility** — the agent critiques the same draft forever, each pass marginally rephrased, never converging. Token bill explodes. Final answer is no better than the first.
2. **Sycophantic self-endorsement** — the agent agrees with its own wrong answer because the critique prompt asks "is this good?" and the model says "yes." Pass rate on the second pass is statistically identical to the first.

A third, subtler symptom shows up only under stress: when the user pushes back ("are you sure?"), the model flips from a correct answer to a wrong one to be agreeable.

## Root cause

Three mechanisms, each requiring a different fix. They are not the same problem.

### Mechanism A — Reflexion / generate-critique-revise (Shinn et al., 2023)

The agent has a **trajectory** (a sequence of thought / action / observation triples) and a **final answer**. Self-correction happens at one of three layers:

- **Step layer** — every tool result gets a verifier (compile passes? schema matches?). Cheap. Catches local errors. Fails on structural mistakes that only show up at the trajectory level.
- **Sub-task / CRITIC layer** — before any *side-effect* action (write file, send email, charge card), a separate critic prompt runs against the original goal. Adds fixed overhead per checkpoint.
- **Trajectory / Reflexion layer** — after a full attempt fails, the agent writes a verbal self-critique, stores it in episodic memory, and starts the next attempt with the critique in context. Improves HumanEval pass@1 from ~80% to **91%** with GPT-4 (the standard reference number). Expensive: every retry is a full run.

The 2026 production pattern is to **stack all three**, each at a different granularity. OpenHands, Devin, Claude Code, and Cursor Composer all do this. Reflexion alone is the wrong tool for step-level errors; a ReAct verifier is the wrong tool for whole-trajectory structural failures.

### Mechanism B — The self-correction blind spot

Recent (2026) work shows LLM agents reliably correct errors presented **externally** but fail to correct identical errors in their **own** reasoning trace. Across 13 model-domain cells covering 7 model families, re-labeling a claim from the agent's own `<thought>` block to a `<memory>` block or a `user` message lifts explicit-correction rate by **23 to 93 percentage points**. 64.5% average blind-spot rate in non-reasoning models.

Practical consequence: **the same model in the same session cannot reliably self-edit its own thoughts**. Two operational fixes work today:

- Inject the draft into a *different role* (user message, tool result) so the model treats it as external. The role label is the controllable variable.
- Append a single word "Wait" before the critique. Reduces the blind spot by ~89% in the published benchmark. Treats it as a diagnostic probe.

### Mechanism C — The sycophancy and skepticism traps

Self-critique methods reduce sycophancy from ~11% (CoT-only) to 7-9% (Reflexion / Self-Refine). They do not eliminate it, because the model critiques itself with the same biases that produced the error. The trace-output gap — the model derives the right answer internally then writes a different, more agreeable one — accounts for 61-78% of pressure-induced errors.

**Fix that works**: route the critique through a **different model** (different family or different temperature) or, better, an **independent judge with no gold labels** that checks trace-output consistency instead of "is this right." Outcome-based self-correction is structurally biased; process-based verification is not.

## The Anthropic 2026 production pattern

The currently shipping version of "self-improving agent" in Claude Managed Agents (announced May 2026) is three features stacked:

1. **Outcomes** — developer defines a rubric; a separate *grader agent* in a fresh context window scores the working agent's output against the rubric. Loop until the rubric is met. The grader's independence from the working session is the load-bearing part.
2. **Dreaming** — a scheduled process that reviews past sessions, extracts recurring mistakes and shared preferences, and writes them as plain-text "playbooks." No weight updates; everything is auditable markdown in the repo.
3. **Multi-agent orchestration** — lead agent decomposes, specialist agents (each its own model, system prompt, context) execute, every step traceable in the console.

The lesson for the rest of us: **separate the critic from the actor, separate the memory write from the actor's run, and ground the critic in a rubric or a tool result, not in the actor's own opinion.**

## Verification

To check a self-correction loop is doing real work, not just adding cost:

1. **A/B on the same prompt set**, comparing pass rate and average tokens, with iteration cap identical across arms. Self-correction that does not move pass rate by ≥5 points is paying for nothing.
2. **Track the verdict token**. Force the critic to reply with a literal `PASS` or a structured failure list. If the agent can be steered to `PASS` by rephrasing the draft, your critic is not grounded.
3. **Run the critique through a different model**. If the second pass equals first pass with both critics, the loop is bias-amplifying. If it equals first pass with one critic and improves with another, the critic is the bottleneck.
4. **Replay a known failure**. After Reflexion, retry a question the original attempt got wrong. The reflection should appear in context. If it doesn't (or the model ignores it), the memory write path is broken.

## Gotchas

- **Iteration caps are non-negotiable.** Hard-cap at 3. A self-critic will always find *something* to improve; an unbounded loop never terminates.
- **The critic needs the original goal, not just the draft.** A critic that only sees the draft invents problems to fix. Always pass the task prompt alongside the draft.
- **Self-critique on a model that just produced the answer is structurally biased.** Use a different model, a fresh context, or a tool-grounded check (tests, schema, lint, search).
- **Reflexion multiplies token cost by N retries.** Budget accordingly; cap retries at 2 for most tasks.
- **Reflection does not help on trivial tasks.** Gate it. Code generation and structured output: yes. Simple lookups: no. A `task_type` flag is enough.
- **"Wait" works** as a one-token intervention to wake the model up to its own error. Document it in the prompt template; do not rely on the model volunteering it.
- **Reflexion memory grows**. Once the lesson buffer exceeds what fits in context, move to a vector store and retrieve only the relevant lessons per task. Do not paste all lessons on every call.
- **Role label matters more than content.** A wrong claim labeled as `<thought>` is corrected far less than the byte-identical claim labeled `<memory>` or `user`. This is a harness artifact, not a capability gap — exploit it.

## Related

- `documentation/docs/policies/lessons/agent-iteration-discipline.md` — when to stop iterating on a task
- `documentation/docs/policies/lessons/lazy-fail-evidence-discipline.md` — same discipline, applied to verification
- `documentation/docs/policies/lessons/scope-discipline.md` — keep self-correction concerns out of unrelated PRs
- `documentation/docs/policies/patterns/multi-agent-orchestration.md` — the topology that makes an independent critic possible
- `documentation/docs/policies/patterns/agent-context-engineering-2026.md` — where the reflection memory lives
- `documentation/docs/policies/patterns/agent-cost-optimization.md` — Reflexion's N× cost is a budget line item
- `documentation/docs/policies/patterns/agent-skill-design.md` — the Claude Code "self-improving skills" pattern is a special case of this lesson

## Source URLs (verified 2026-08-09)

- Reflexion paper, Shinn et al. 2023 — https://arxiv.org/abs/2303.11366
- Agent-R (iterative self-training for reflection) — https://arxiv.org/abs/2501.11425
- RePro (retrospective progress-aware refinement) — https://arxiv.org/abs/2606.14302
- Multi-Agent Reflexion (MAR) — https://arxiv.org/abs/2512.20845
- Self-correction blind spot (relabeling lifts correction 23-93 pp) — https://arxiv.org/abs/2606.05976
- Sycophancy and skepticism in LLM causal judgment (RCA) — https://arxiv.org/abs/2601.08258
- Anthropic Code with Claude 2026: dreaming + outcomes + multi-agent — https://venturebeat.com/technology/anthropic-introduces-dreaming-a-system-that-lets-ai-agents-learn-from-their-own-mistakes
- Anthropic: When AI builds itself (recursive self-improvement) — https://www.anthropic.com/institute/recursive-self-improvement
- "Self-Correcting Agents: Reflexion, CRITIC, ReAct compared (2026)" — https://callsphere.ai/blog/self-correcting-agents-reflexion-critic-react-loops-compared-2026
- Taskade: Self-Improving AI Agents, the Reflection Loop — https://www.taskade.com/blog/self-improving-ai-agents-reflection
- Sandbase: Building a Self-Correcting AI Agent — https://www.sandbase.ai/blog/building-self-correcting-ai-agent-advanced-memory-reflection/
- "ReAct vs Plan-and-Execute vs ReWOO vs Reflexion" — https://theaiengineer.substack.com/p/the-4-single-agent-patterns
- "Self-Reflection in LLM Agents: Effects on Problem-Solving" (Renze & Guven, 2024) — https://arxiv.org/abs/2405.06682
