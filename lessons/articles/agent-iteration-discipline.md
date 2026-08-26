# agent-iteration-discipline

**Issue:** How an agent should iterate — the loop, the eval, the stop conditions
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 196e96e
**Author:** the platform team
**Status:** verified-live (https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)

## Symptom

The agent works on a hard task. It writes code, runs it, it
fails. It edits. Still fails. It edits again. After 20 commits
of "fixes," the code is in worse shape than the original.
The agent declares "done!" The user discovers the bug
unfixed. The agent retries. The user is now babysitting. The
fix is force-pushed, breaking history. The user loses trust
in the entire system. The team reverts everything. Three days
lost.

## Root cause

**Iteration is a control loop with a stop condition, not a
hope-and-iterate loop.** The agent loop has 5 documented stop
conditions; without them, the agent will retry forever. Eval
is what tells you whether each iteration is making things
better or worse. Without a baseline + threshold + gate, the
agent has no oracle. The 5+6 stages closure spec from the
repo's own `lazy-fail-discoveries.md` is the right shape, but
the meta-frame is missing: how to know WHICH stage you're
in, when to stop, and when to escalate.

**Source:** Anthropic:
- Demystifying evals for AI agents: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Agent SDK — agent loop: https://code.claude.com/docs/en/agent-sdk/agent-loop
- How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works
- Research on Claude Code (arxiv 2604.14228): https://arxiv.org/html/2604.14228v1

**Source:** Industry:
- Eval-Driven Development (perea.ai): https://www.perea.ai/research/eval-driven-development-agents
- Red Hat — eval-driven development 2026: https://developers.redhat.com/articles/2026/03/23/eval-driven-development-build-evaluate-ai-agents
- Self-correcting agent loop in CI (Samuel Fajreldines): https://www.samuelfaj.com/en/blog/when-ci-sends-the-failure-back-to-the-agent/
- Future AGI — What is EDD 2026: https://futureagi.com/blog/what-is-eval-driven-development-2026/
- AI Agent Evaluation 2026 (digitalapplied): https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology
- Mastra — AI Agent Evaluation: https://mastra.ai/articles/ai-agent-evaluation
- Gravity AI — Regression Testing: https://gravity.fast/blog/ai-agent-regression-testing-guide/
- 6 building blocks of an agentic loop (YouTube): https://www.youtube.com/watch?v=D7TIvqtSZQE

**Source:** This repo:
- `documentation/categories/lessons/lazy-fail-discoveries.md` — the L1-L5 rules
- `documentation/categories/lessons/lazy-fail-evidence-discipline.md` — the evidence rules
- `packages/fleet/LESSONS.md` — the 8 own-failure lessons
- `packages/fleet/src/eval-harness.js` — the implementation
- `packages/fleet/src/self-improve.js` — the loop

## The "agent loop" concept

The Anthropic SDK runs an **agent loop** (the same loop that
drives Claude Code) with 5 steps:
1. **Receive prompt** + system prompt + tool definitions + conversation history
2. **Evaluate and respond** — text, tool calls, or both
3. **Execute tools** — SDK runs each, collects results
4. **Repeat** steps 2-3 as a cycle. One full cycle = one **turn**.
5. **Return result** when Claude produces output with no tool calls

A `turn` = one round trip inside the loop. Turns continue
until Claude produces output with no tool calls, OR one of
the 5 stop conditions fires.

**Self-correction happens automatically.** When a tool
returns an error, Claude sees it and adjusts on the next turn.
You don't write retry logic — the loop handles it.

## The "5 stop conditions" concept

The agent loop terminates on (per arxiv 2604.14228):
1. **No tool use** — the primary stop condition; model produces only text
2. **Max turns** — `max_turns` / `maxTurns` config limit reached
3. **Context overflow** — `prompt_too_long` after recovery attempts fail
4. **Hook intervention** — a PostToolUse hook sets `hook_stopped_continuation`
5. **Explicit abort** — `abortController` signal fires

You can also cap by **spend** via `max_budget_usd` /
`maxBudgetUsd`. Setting a budget is the default for production
agents because it bounds the most expensive failure mode
(infinite loop on a hard task).

**Operational rule:** always set `max_turns` and
`max_budget_usd` for production agents. Without them, an
open-ended prompt ("improve this codebase") can run for
hours and rack up thousands of dollars.

## The "iteration discipline" concept

**The 5+6 stages closure spec (from this repo's `lazy-fail-discoveries.md`):**
1. Official doc
2. Claim review (sub-agent)
3. Live curl
4. Sibling regression
5. Independent verifier
6. Live post-deploy

This is **one iteration's closure**. An agent runs this loop
**many times** in a session. The discipline is what keeps
each iteration from drifting.

**The 4 rules (synthesized from this repo's lessons + the Anthropic loop):**

1. **L1 SHIP OR EXPLAIN** — every iteration returns a merged artifact / opened PR / new finding / explicit blocker. Never "nothing to do." (from `lazy-fail-discoveries.md`)
2. **L2 NO STABLE/IDLE** — if the loop is empty, run recon, file ≥ 1 finding per cycle. (from `lazy-fail-discoveries.md`)
3. **L3 USER-PIVOT** — destructive operations (force-push, delete branch, revert) require explicit user approval. (from `lazy-fail-discoveries.md` + `user-pivot-rule.md`)
4. **L4 EVIDENCE REQUIRED** — every claim has curl evidence or real code grep. No "I think." (from `lazy-fail-discoveries.md` + `lazy-fail-evidence-discipline.md`)

**Plus the 8 lessons from this repo's `fleet/LESSONS.md` (postmortem on building the system):**
- Guessed instead of researching — search the SPECIFIC mechanism, not the category
- Built infrastructure instead of delivering — ship the simplest working version FIRST
- Didn't capture lessons as they happened — capture every failure IMMEDIATELY
- Model output format mismatch — test the actual output format before building a parser
- Full-file overwrite instead of diff — partial changes applied as diff, not overwrite
- Semantic search missed named files — when issue body names a file, add to allowlist
- Comments truncated — per-tier token limits + truncation detector
- Bot-sounding comments — match the user's voice, no "Automated" labels

## The "self-correcting loop in CI" pattern

For a CI-driven agent that fixes its own failures (per Samuel Fajreldines), the loop MUST have:

1. **The failure** that triggered the workflow
2. **The command** that reproduces it
3. **The file scope** the agent may touch
4. **The success condition**
5. **The stopping rule** — `attempts: 2`, `stop_if: ["the same failure appears twice", "the patch touches a file outside scope", "the fix requires a secret"]`

```yaml
# A repair contract for an agent
failure: "session-renewal test failed"
command: "npm run test -- session-renewal"
evidence: ".ci/failures/session-renewal.log"
allowed_scope:
  - "src/auth/session.service.ts"
  - "tests/auth/session-renewal.spec.ts"
success:
  - "the failed command passes again"
  - "npm run typecheck still passes"
limits:
  attempts: 2
  no_database_migration: true
  no_secret_change: true
stop_if:
  - "the same failure appears twice"
  - "the patch touches a file outside scope"
  - "the fix requires a secret"
```

**Two attempts is a good default.** Three is too many —
persistence past two attempts usually means a wrong
diagnosis, not a stubborn bug.

**If the second attempt fails for the same reason → call a
person.** Don't loop further; the fix needs judgment.

## The "eval-driven development (EDD)" concept

**Eval-Driven Development** is the practice — explicitly
endorsed as Anthropic's official practice — of writing eval
suites BEFORE agent code, gating every PR against a baseline
through automated CI checks, and treating the eval suite as
the executable specification of correct agent behavior.

**The TDD → EDD mapping (per perea.ai):**
| TDD | EDD |
|---|---|
| Write a failing unit test | Write an eval that scores a baseline agent (low pass rate is the feature) |
| Write code to pass the test | Iterate on prompts, tools, model choice until the suite passes at threshold |
| Refactor without breaking tests | Swap models, prompts, or tools while maintaining eval scores |
| Run tests on every commit | Run evals on every PR via CI/CD |
| Fix regressions immediately | Catch score drops before deployment |

## The "4-step EDD loop" pattern

1. **Write the eval first** — capture the desired behavior; include at least one case the current prompt fails
2. **Run against the current prompt** — observe the baseline; save it
3. **Iterate the prompt or model** — change one variable at a time (prompt body, model id, temperature, tool definitions); re-run; track the per-rubric delta
4. **Refactor the suite** — when the eval passes threshold, tighten: add adversarial cases the current prompt handles correctly but a future regression might break; retire cases that no longer reflect the workload

The eval suite is the source of truth for what "working"
means on the workload, and it grows as the workload matures.

## The "golden dataset" pattern

**20-50 tasks is the right starting point** (Anthropic's
recommendation). Sourced from real failures, not curated
wishlists. Two domain experts should independently reach
the same pass/fail verdict on a task; if they would
disagree, the task is ambiguous and an ambiguous task
produces an unreliable grader.

**Three buckets to cover:**
- **Happy paths** — standard inputs where the agent should succeed cleanly
- **Edge cases** — unusual inputs, missing data, ambiguous instructions
- **Adversarial cases** — prompt injections, contradictory instructions, refusal-required scenarios

**Plus a fourth implicit bucket:** every production failure
becomes a test case. Over time the test suite becomes a map
of every failure mode the agent has encountered, and CI
prevents each from recurring.

## The "two grader classes" pattern

| Grader | Use when | Examples | Cost |
|---|---|---|---|
| **Code-based (deterministic)** | Outcome is verifiable | String match, JSON schema, regex, lint, state check (SQL row exists) | Free, fast, reliable |
| **LLM-as-judge (semantic)** | Outcome is qualitative | Rubric scoring, style, completeness, harm | Claude Haiku 4 ~$0.80/M tokens is the 2026 default; gpt-4o-mini is the cheapest credible alternative |

**Best practice:** combine both. Hard checks for
deterministic things; LLM judge for the fuzzy parts. The
LLM judge itself needs calibration against a human gold set
before you can gate on it.

**Run each case multiple times.** A single run can pass or
fail by luck. 5 runs give you a rate you can trust. Report
both `pass@k` (capability — did the agent ever succeed?) and
`pass^k` (reliability — did the agent succeed consistently?).

## The "capability vs regression" eval pattern

- **Capability (quality) evals** ask "What can this agent do well?" Start at low pass rate, target hard tasks, give teams a hill to climb.
- **Regression evals** ask "Does the agent still handle all the tasks it used to?" Should have nearly 100% pass rate. Protect against backsliding.

**Maintain two suites.** As you hill-climb on capability,
regression evals catch cross-cutting damage. When a
capability eval hits 100% for multiple consecutive months,
**graduate it** into the regression suite. Saturated evals
don't become useless; they become guardrails.

## The "6-component CI gate" pattern

For a production eval CI gate (per perea.ai):

1. **Test runner** — orchestrates 50-100 concurrent API calls; eval time < 5 min/run
2. **Model under test** — the candidate model/prompt combo. Harness must abstract the model interface so swaps don't require eval rewrites.
3. **Deterministic scorer** — exact match, JSON schema, regex, label accuracy, latency budget, cost budget
4. **LLM-as-judge scorer** — semantic criteria with explicit rubrics
5. **Baseline results store** — per-example results from current production. Candidate runs compute deltas against this anchor, not just aggregate scores.
6. **CI gate** — blocks merge on >3% aggregate drop, or >1% drop on any specific category (safety, refusals). Posts a PR comment with the diff.

**Path filter:** trigger evals only when `paths: ['src/prompts/**', 'src/agents/**']` matches, not on every commit. Reduces eval CI runs by 80-90% while catching all prompt-related regressions.

## The "5-stage eval pipeline" pattern

For CI-driven iteration (per Luong Hong Thuan / AgentMarketCap):

1. **Lint** — basic config sanity
2. **Smoke** — 1 example; fast feedback
3. **Comprehensive** — full set with budget ceiling
4. **Delta vs production baseline** — per-example diff
5. **PR comment** — table of results, pass/fail by category

Merge is blocked if any regression-blocking metric drops
below the prior baseline.

## The "the agent loop and EDD together" pattern

The agent loop handles **single-task iteration**:
- "Fix this bug" → 1-N turns → result

EDD handles **workload-level iteration**:
- "Improve the agent" → many evaluations → 1 PR with prompt + tool + model changes

**The two are complementary.** The agent loop has its 5
stop conditions; EDD has its 4-step loop. An agent operating
under EDD runs the inner loop many times, each iteration
scored by the eval suite, with the EDD loop wrapping the
outer iteration.

## The "6 building blocks of a self-correcting agentic loop" pattern

(From the YouTube talk on loop engineering)

1. **Trigger** — slash skill, schedule, GitHub event, file watch
2. **Worktree** — isolated branch/environment per iteration
3. **Skills** — loadable instructions for execution + review
4. **Connectors** — MCPs / CLIs to external systems (Stripe, Supabase, etc.)
5. **Memory** — persistent state across iterations (GitHub Issues, project memory, lessons)
6. **Sub-agents** — delegation boundaries for parallel work

The fleet (`packages/fleet/`) implements all 6:
- Trigger: GitHub issue
- Worktree: `safety.createBranch(issue)` + git isolation
- Skills: the 4 zcode-plugin skills
- Connectors: `packages/connectors/` (real-providers, credentials, pool, transports)
- Memory: `packages/shared-memory/` (per-project MEMORY.md + runs/)
- Sub-agents: would be the `Agent` tool invocations within a fleet run

## The "iteration anti-patterns" anti-patterns

### 1. Infinite retry on a hard task
- **Issue:** Agent loops 50+ times on a wrong diagnosis
- **Fix:** `max_turns: 10`, `max_budget_usd: 5`, explicit stop conditions

### 2. Fixing the same failure differently each time
- **Issue:** Agent keeps editing the same code in different ways; passes baseline by luck
- **Fix:** Golden set with deterministic graders; if same failure twice, call a person

### 3. Declaring "done!" without verification
- **Issue:** Agent stops at the first "looks good" without running the test
- **Fix:** Eval harness is the oracle, not the agent's self-assessment; gate on green

### 4. No baseline to compare against
- **Issue:** Agent can't tell if iteration is making things better or worse
- **Fix:** Save baseline results; compute deltas per iteration; threshold-gate merges

### 5. Edits outside scope
- **Issue:** Agent "drive-by refactors" while fixing a bug; the refactor introduces a new bug
- **Fix:** Explicit `allowed_scope` in the repair contract; reviewer blocks diffs outside it

### 6. Capturing failures only when the user asks
- **Issue:** Lessons are lost between sessions
- **Fix:** `PostToolUseFailure` hook (this repo's pattern) — capture immediately

### 7. Force-pushing / deleting branches to "fix" iteration
- **Issue:** User loses history; can't audit what changed
- **Fix:** Branch protection + user approval for destructive ops (the L3 user-pivot rule)

### 8. Periodic eval, not continuous
- **Issue:** Eval runs once a sprint; regressions ship undetected
- **Fix:** CI gate on every PR that touches prompts, agents, or tools

### 9. Optimizing the wrong metric
- **Issue:** Agent optimizes for "looks good" while regressing on safety
- **Fix:** Per-category metrics; safety is must-pass, quality is threshold

### 10. Saturation blindness
- **Issue:** Capability eval hits 100%, agent "graduates," eval removed — then a regression goes unnoticed
- **Fix:** Graduate saturated evals to the regression suite, don't delete them

## The "5+6 stages closure, in the iteration frame" pattern

The repo's `lazy-fail-discoveries.md` says:
- Stages 1-5 (official doc, claim review, live curl, sibling regression, independent verifier) = pre-merge
- Stage 6 (live post-deploy) = post-merge

**The iteration frame makes this concrete:**

| Stage | What | When | How to verify |
|---|---|---|---|
| 1. Official doc | Read the spec before writing code | Pre-implementation | URL + date in PR |
| 2. Claim review | Sub-agent reviews your work | Pre-PR | Sub-agent verdict in PR |
| 3. Live curl | Run the actual command, don't trust memory | Pre-PR | curl output in PR |
| 4. Sibling regression | Check the 3 other places the same pattern exists | Pre-PR | grep results in PR |
| 5. Independent verifier | Different session, different eyes | Pre-merge | Verifier session id in PR |
| 6. Live post-deploy | Verify in production | Post-merge | `curl <prod URL>` and expected output |

**Each iteration that closes stages 1-5 is a candidate PR.**
Stage 6 happens after merge. A loop that closes stages 1-5
twice in a row is a *stable iteration*, not a fluke.

## The "iteration checklist" pattern

For every iteration:

- [ ] Set `max_turns` and `max_budget_usd` on the agent loop
- [ ] Define the failure being fixed (concrete command + log path)
- [ ] Define the allowed scope (file paths, no-DB-migration, no-secret-change)
- [ ] Define the success condition (the test passes, lint passes, typecheck passes)
- [ ] Define the stopping rule (`attempts: 2`, same failure twice → call a person)
- [ ] Run baseline eval before changing anything
- [ ] Change one variable at a time; re-run eval after each change
- [ ] Save transcript of every iteration; read failed transcripts
- [ ] Capture every failure immediately (PostToolUseFailure hook or equivalent)
- [ ] Edits outside scope = block; force-push = block; revert = user-approval
- [ ] PR with stages 1-5 evidence in body; stage 6 after merge
- [ ] When eval passes threshold, tighten the suite (add adversarial cases)
- [ ] Graduate saturated capability evals to the regression suite

## Verification
- **Test:** Agent loop terminates on a stop condition (not on resource exhaustion)
- **Test:** Every iteration has a baseline → change → delta
- **Test:** `max_turns` and `max_budget_usd` set on every production agent
- **Test:** Golden set grows when production failures occur
- **Test:** Saturated capability evals graduate, not delete
- **Test:** PR body has stages 1-5 evidence
- **Audit:** Re-read Anthropic's "Demystifying evals" quarterly (eval methodology is moving fast)

## Gotchas
- **The "infinite retry" anti-pattern.** Set `max_turns` and `max_budget_usd`.
- **The "no baseline" anti-pattern.** Save baselines; compare deltas.
- **The "drive-by refactor" anti-pattern.** `allowed_scope` + reviewer gate.
- **The "periodic eval" anti-pattern.** Continuous, on every PR.
- **The "single-source research" anti-pattern.** Cross-check with 2+ sources.
- **The "saturation blindness" anti-pattern.** Graduate, don't delete.
- **The "scope-less fix" anti-pattern.** Edit budget + file allowlist.
- **The "destruction without approval" anti-pattern.** Force-push / delete / revert = user-approval gate.

## Related
- `documentation/categories/lessons/lazy-fail-discoveries.md` — the L1-L5 rules this entry synthesizes
- `documentation/categories/lessons/lazy-fail-evidence-discipline.md` — the evidence rules
- `documentation/categories/lessons/scope-discipline.md` — applies to iteration: one PR = one concern
- `documentation/categories/lessons/user-pivot-rule.md` — user approval for destructive ops
- `documentation/categories/lessons/when-to-ask-vs-push.md` — push on reversible, ask on irreversible
- `documentation/categories/lessons/example project-audit-2026-08.md` — the 30 real findings that the eval suite should catch
- `documentation/categories/patterns/agent-skill-design.md` — SKILL.md design
- `documentation/categories/patterns/mcp-server-patterns.md` — MCP tool design (eval applies to tools too)
- `packages/fleet/LESSONS.md` — the 8 own-failure lessons from building the system
- `packages/fleet/src/eval-harness.js` — the implementation
- `packages/fleet/src/self-improve.js` — the 4-step loop
- `packages/fleet/src/safety.js` — the risk classification that gates force-push
- `packages/fleet/src/reviewer.js` — the BLOCK/WARN/OK reviewer

**Source URLs (verified 2026-08-09):**
- Anthropic — Demystifying evals for AI agents: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- Anthropic — Agent SDK agent loop: https://code.claude.com/docs/en/agent-sdk/agent-loop
- Anthropic — How Claude Code works: https://code.claude.com/docs/en/how-claude-code-works
- arxiv 2604.14228 — Design Space of Claude Code: https://arxiv.org/html/2604.14228v1
- perea.ai — Eval-Driven Development for AI Agents: https://www.perea.ai/research/eval-driven-development-agents
- Red Hat — eval-driven development 2026: https://developers.redhat.com/articles/2026/03/23/eval-driven-development-build-evaluate-ai-agents
- Future AGI — EDD 2026: https://futureagi.com/blog/what-is-eval-driven-development-2026/
- Samuel Fajreldines — self-correcting loop in CI: https://www.samuelfaj.com/en/blog/when-ci-sends-the-failure-back-to-the-agent/
- digitalapplied — AI Agent Evaluation Pipeline 2026: https://www.digitalapplied.com/blog/ai-agent-evaluation-pipeline-2026-testing-methodology
- Mastra — AI Agent Evaluation: https://mastra.ai/articles/ai-agent-evaluation
- Braintrust — EDD: https://www.braintrust.dev/articles/eval-driven-development
- Gravity AI — AI Agent Regression Testing: https://gravity.fast/blog/ai-agent-regression-testing-guide/
- arxiv 2602.18029 — Towards More Standardized AI Evaluation: https://arxiv.org/html/2602.18029v1
- AI Agents 2026 — Tools, Memory, Evals, Guardrails: https://andriifurmanets.com/blogs/ai-agents-2026-practical-architecture-tools-memory-evals-guardrails
- The 6 building blocks of an agentic loop: https://www.youtube.com/watch?v=D7TIvqtSZQE
- State of AI Agents 2026 (Lovelytics): https://lovelytics.com/post/state-of-ai-agents-2026-lessons-on-governance-evaluation-and-scale/
