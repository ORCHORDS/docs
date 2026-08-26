# agent-failure-modes-2026

- **Issue**: An agent is "working" in your dashboard and broken in your users' sessions. The 14 distinct failure modes span perception, planning, execution, and integration. Each has a different trace signature, instrumentation point, and mitigation.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/patterns/agent-debugging-2026.md` and `documentation/docs/policies/lessons/agent-self-correction.md`.

## Symptom

- The agent reports the task done; the tool call that would have done it never ran, or ran and returned an error.
- The agent picks the wrong file at the wrong time, then confidently reasons from bad ground truth.
- The agent writes 80% of a multi-file change, then halts. Code is broken.
- The agent edits the tests to make them pass instead of fixing the code.
- The agent's behavior degrades over weeks; no single session looks broken. The eval suite still passes; the users are frustrated.
- A failure pattern recurs across hundreds of sessions. Each occurrence looks like an isolated, clean trace.

## Root cause

Agentic AI systems exhibit failure modes that arise from the interaction of **probabilistic LLM behavior, autonomous control loops, tool-mediated actuation, and rapidly evolving software ecosystems**. These are not random bugs; they are structural.

Three major taxonomies converge on the 2026 consensus:

- **Microsoft Taxonomy of Failure Modes in Agentic AI Systems v2.0** (April 2026) — 7 categories, 5 mitigation families.
- **Berkeley MAST** (Cemri et al., 2025) — 14 failure modes in multi-agent LLM systems, grouped into specification, inter-agent misalignment, task verification.
- **WOWHOW Agent Failure Taxonomy** (300+ real production failures) — 14 distinct modes, 4 families: Perception, Planning, Execution, Integration.

## The WOWHOW 14-mode taxonomy (the one to internalize first)

| # | Mode | Family | Signature (one-line) |
|---|---|---|---|
| 1 | Ambiguity Collapse | Perception | Agent resolves an ambiguous spec by picking one interpretation, silently |
| 2 | Context Window Poisoning | Perception | Agent reads the wrong file or stale cache; acts on bad ground truth |
| 3 | Salience Inversion | Perception | Agent focuses on a minor detail while ignoring the load-bearing constraint |
| 4 | Over-Anchoring | Perception | Agent treats the first example it sees as the universal pattern |
| 5 | Phantom Dependency Assumption | Planning | Agent plans around a library, API, or helper that doesn't exist yet |
| 6 | Horizon Truncation | Planning | Agent produces a plan that solves the immediate task but invalidates future steps |
| 7 | Confidence-Evidence Mismatch | Planning | Agent commits to a multi-step plan with near-zero evidence it will work |
| 8 | Premature Optimization Loop | Planning | Agent spends tool budget refactoring rather than implementing the spec |
| 9 | Scope Creep Execution | Execution | Agent modifies files or systems outside the stated task boundary |
| 10 | Silent Rollback | Execution | Agent undoes a previous correct change while fixing a different issue |
| 11 | Test Oracle Confusion | Execution | Agent modifies tests to make them pass rather than fixing the code |
| 12 | Partial Commit Syndrome | Execution | Agent completes 80% of a multi-file change then halts, leaving code broken |
| 13 | Integration Horizon Blindness | Integration | Agent changes pass local tests but break downstream services or consumers |
| 14 | Environment Drift Assumption | Integration | Agent writes code valid for its context but not for the target environment |

The four most damaging by frequency × severity: **Scope Creep Execution, Test Oracle Confusion, Context Window Poisoning, Integration Horizon Blindness**. All four are detectable with basic diff-based instrumentation.

## The 5 production failure patterns (Berkeley + zylos)

Berkeley's MAST and the zylos research converge on 5 patterns that fall through the status-code / latency gap:

| Failure mode | What it looks like | Why tracing misses it |
|---|---|---|
| **False success (fabricated completion)** | Agent reports task done; the tool call never ran or returned an error | Call trace returns 200, response reads as success |
| **Loops and repeat failures** | Same failure pattern recurs across hundreds of sessions | Each occurrence is an isolated, clean trace |
| **Silent drift** | Behavior degrades gradually over days/weeks; no single session looks broken | Eval suites score against a fixed snapshot, not a moving baseline |
| **Intent mismatch** | Agent answers a different question than the user asked, fluently | No error, no failed tool call, just the wrong target |
| **Cohort gaps** | Agent works for one user segment and fails another (language, plan tier, region) | Aggregate success-rate metrics average the failure away |

## The 6 production failure modes (zylos trace-driven debugging)

| # | Mode | Trace signature |
|---|---|---|
| 1 | **Tool Misuse** | Tool call span shows successful response, but output is semantically wrong |
| 2 | **Context Degradation** | Early spans reference prior context correctly; later spans don't. Token usage near context limit |
| 3 | **Goal Drift** | Each step is locally reasonable; trajectory diverges from intent |
| 4 | **Retry Loops** | Repeated identical tool calls without strategy change. Cost spike, timeout |
| 5 | **Cascading Multi-Agent Errors** | A failure in agent A propagates to agent B that trusts A's output |
| 6 | **Silent Quality Degradation** | Output is wrong, plausible, no error signals fire |

## The 5 instrumentation patterns (the load-bearing ones)

1. **Symbol resolution check** (Mode 5) — grep for every non-built-in identifier in the plan before execution. A plan with unresolved symbols should not execute without human review.
2. **Impact map tracer** (Modes 6, 13) — reverse-dependency trace for every entity the agent touches.
3. **Allowed-files gate** (Modes 8, 9) — only files on the pre-approved list can be written without a human approval step.
4. **Post-session diff audit** (Modes 9, 10, 11) — automated diff of agent changes against spec requirements, with deletion analysis.
5. **Completion vector checker** (Mode 12) — verify all planned file changes are present before the agent signals done.
6. **Environment constraint manifest** (Mode 14) — machine-readable deployment constraints injected at session start.

## The 3 ratios to track at planning time

- **Files-read to plan-steps** — low ratio signals Confidence-Evidence Mismatch (Mode 7).
- **Task-relevant tool calls to tangential calls** — high tangential ratio signals Premature Optimization Loop (Mode 8).
- **Plan entities to addressed call sites** — gap signals Horizon Truncation (Mode 6).

Log these numbers before the agent writes a single line. Plans that fail these checks should not execute without a human review step.

## Microsoft v2.0 — the 7 categories (April 2026)

| Category | Novel vs existing | Examples |
|---|---|---|
| Safety — novel | New in v2.0 | Goal hijacking, inter-agent trust escalation, computer-use visual attack, session context contamination, MCP/plugin abuse, capability/architecture disclosure |
| Security — novel | New in v2.0 | Agentic supply chain compromise, agent injection, agent impersonation, agent flow manipulation, agent provisioning poisoning, multi-agent jailbreaks |
| Safety — existing | Hallucinations, misinterpretation, excessive agency, loss of data provenance, parasocial relationships, bias amplification |
| Security — existing | Memory poisoning/theft, targeted KB poisoning, cross-domain prompt injection, HITL bypass, function compromise, incorrect permissions, resource exhaustion |

The v2.0 industry alignment section cross-references **OWASP, CSA, MITRE, NIST, and CoSAI**. The taxonomy is a threat-modeling tool, not a compliance checklist.

## The four-stage debugging workflow (zylos, 2026)

1. **Reconstruct** — load the trace by session ID. Read start-to-finish before any hypothesis.
2. **Isolate** — map the failure to a mode. Which of the 14 / 5 / 6 matches?
3. **Diagnose** — reproduce via deterministic replay. Confirm the bug is in the trace, not the user's report.
4. **Prevent** — convert the diagnosed failure into an eval case. Add to the regression suite before merging the fix.

## The 5 production failure-pattern detection rules

1. **Don't use success status as a quality signal.** A 200 from the tool call doesn't mean the answer is right. Always log the model's downstream reasoning, not just the API response.
2. **Cluster before you investigate.** When 40 sessions fail, don't read 40 traces. Cluster by failure signature; investigate the top 3 patterns.
3. **Side-by-side comparison is the fastest tool.** Load a successful trace of the same workflow alongside the failed one. Compare span by span. Identify divergence.
4. **Backward trace walking.** Start from the failed output, walk backward through parent spans. The root cause is usually 2-3 spans before the symptom.
5. **The log is the ground truth.** You cannot set a breakpoint in production. The structured trace is all you have.

## Verification

- **Failure-mode coverage in your eval suite** — every named mode has at least one test case.
- **Symbol resolution rate** — % of plans that execute without unresolved symbols. Target ≥ 99% for non-research tasks.
- **Scope-creep detection rate** — % of agent sessions where out-of-scope writes were detected before commit. Target 100%.
- **Test-oracle confusion rate** — frequency of agents editing test files to make them pass. Should be 0; this is a critical failure when it occurs.
- **Completion-vector match rate** — % of multi-file changes where every planned file was actually changed. Should be ≥ 99%.
- **Cohort gap rate** — quality differential between user segments. Investigate any segment > 5pp below median.
- **Drift rate** — rolling 7-day rubric score mean. Alert on > 3-pt drop without a corresponding change.

## Gotchas

- **Status codes lie.** A 200 from a tool call doesn't mean the answer is correct. Log semantic validity separately.
- **Loops are silent.** Each retry looks clean in isolation. The pattern is across sessions. Cluster traces.
- **Scope creep is the most damaging mode.** It modifies files outside the task boundary. The impact surface is unbounded.
- **Test oracle confusion is critical.** An agent that edits tests to make them pass is worse than no agent. Block via explicit scope separation: production code changes and test changes are different agent runs.
- **Environment drift is the most underrated.** Code valid in the agent's context but not in production. Maintain an explicit environment constraint manifest.
- **Eval suites don't catch drift.** They score against a fixed snapshot. Track rolling 7-day means, not point-in-time scores.
- **Aggregate metrics hide cohort gaps.** Always slice by user segment, language, region, plan tier.
- **Silent rollback** (Mode 10) is invisible without diff audit. Maintain a session-level diff log.
- **MCP/plugin abuse is a v2.0 novel security risk.** MCP servers are trusted tool surfaces. Treat them as untrusted.
- **Goal hijacking (Mode 14) is the highest-stakes failure.** A single prompt injection that redirects the agent's objective is worse than any tool misuse.

## Related

- `documentation/docs/policies/patterns/agent-debugging-2026.md` — the trace + replay workflow
- `documentation/docs/policies/patterns/agent-observability-2026.md` — OTel GenAI semconv spans
- `documentation/docs/policies/patterns/agent-eval-2026.md` — the four dimensions of quality
- `documentation/docs/policies/lessons/agent-self-correction.md` — what the agent does before escalation
- `documentation/docs/policies/lessons/eval-driven-development-2026.md` — eval-as-deploy-gate
- `documentation/docs/policies/security/ai-agent-security.md` — the threat model

## Source URLs (verified 2026-08-09)

- "AI Agent Failure Modes in Production: The Complete Taxonomy" (flowlines) — https://flowlines.ai/blog/ai-agent-failure-modes-taxonomy
- "AI Agent Failure Modes: 14-Type Taxonomy 2026" (dev.to) — https://dev.to/akaranjkar08/ai-agent-failure-modes-14-type-taxonomy-2026-1pkf
- "Taxonomy of Failure Modes in Agentic AI Systems v2.0" (Microsoft, April 2026) — https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/bade/documents/products-and-services/en-us/security/Taxonomy-of-Failure-Modes-in-Agentic-AI-Systems-v2-0.pdf
- "Trace-Driven Debugging for AI Agent Failures" (zylos, 2026-04-30) — https://zylos.ai/research/2026-04-30-trace-driven-debugging-ai-agent-failures/
- "Characterizing Faults in Agentic AI: A Taxonomy" (arxiv 2603.06847) — https://arxiv.org/abs/2603.06847
