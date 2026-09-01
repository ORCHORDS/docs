# Agent Canary Task Regression Suite

Every change to an agent, a model version bump, a prompt edit, a tool schema tweak, a retrieval index rebuild, carries regression risk, and full evaluation suites are too slow and expensive to run on all of them. A canary task suite is a small, fixed set of tasks run on every change, chosen so that most regressions show up as red within minutes. The craft is in what goes in, what stays out, and what the red signal obligates people to do. This article covers selecting canaries, wiring them into change pipelines, keeping them honest, and handling the inevitable alert fatigue.

## Scope

Applies to engineering teams shipping frequent changes to agent systems: prompt and instruction revisions, model or provider version changes, tool registry updates, and orchestration logic edits. Covers canary selection criteria, execution harness requirements, gating policy, and suite maintenance. Does not cover the broader labeled evaluation corpus, LLM-judge calibration, or trajectory-level rubric design, all of which complement the canary layer at lower frequency and higher depth.

## Workflow or implementation guidance

1. Fix the size first: between 15 and 40 tasks total. A suite that cannot run inside your normal pre-merge window will be skipped the first time a deadline looms, and a skipped suite is a dead suite.
2. Select tasks for maximal sensitivity per slot. Include: one task per major capability family; one task per tool that is on the critical path; adversarial fixtures for the failure classes you have actually shipped (injection resistance, refusal correctness, schema-conformant output under ambiguity); tasks with known brittleness markers such as multi-step reasoning chains; and one end-to-end task exercising the full loop including a human approval or escalation step.
3. Freeze inputs and expected behaviors. Each canary carries its exact input, environment fixture (faked tool backends with canned responses), and a machine-checkable assertion set: final answer checks where determinism is possible, structural checks on output schema, step-count ceilings, required-tool-called assertions, forbidden-tool or forbidden-data-flow assertions, and latency budgets.
4. Ban live external dependencies. Tool calls resolve to recorded fixtures, model sampling where used by assertions is pinned, and network access is denied by default in the harness. A canary that fails because a third-party API had a hiccup teaches the team to ignore red.
5. Gate with tiered severity rather than a single pass-fail. Tier 1 (must-pass): injection resistance, destructive-action confirmation, schema validity, forbidden data flows. A Tier 1 failure blocks the change outright. Tier 2 (quality signals): answer correctness on deterministic tasks, step-count and latency budgets. A Tier 2 failure requires an explicit human decision with a recorded justification. Tier 3 (diagnostic only): verbosity, phrasing drift, token spend, logged but never gating.
6. Run on every candidate change with a stable baseline comparison: the suite runs against both the current production configuration and the candidate in the same harness, and reports diffs, not absolute scores alone. Diff-based reporting keeps slow drift in environmental noise from masquerading as regression.
7. Make failures actionable by construction: every red canary links to its trace, the exact assertion that failed, the fixture version, and the owning team, from the notification itself. If triage requires opening five systems, triage will not happen.
8. Rotate deliberately: when a production incident reveals a failure class with no covering canary, add one and retire the least valuable existing slot in the same change, preserving the size budget. Retired canaries move to the deeper evaluation corpus rather than being deleted.
9. Review the suite quarterly: coverage against the capability map, per-canary historical pass rates, and time-to-run. Any canary that has never failed anything and covers nothing distinctive is a candidate for retirement.

## Controls

- Suite-as-code: canaries, fixtures, and assertions live in version control beside the agent code they protect; changes to the suite get code review like any other change.
- Tamper resistance: disabling a canary or widening a threshold is a visible, reviewed diff, never a runtime configuration someone can flip to get a merge through.
- Determinism monitoring: repeated runs of an unchanged configuration on the fixed suite must agree within documented bounds; unexplained nondeterminism is itself a red condition.
- Ownership map: each canary has a named owner responsible for keeping its fixtures current.
- Time budget: hard wall-clock ceiling on the whole suite, with a breach treated as a defect in the suite.

## Validation evidence

- Historical replay: take the last N production-impacting regressions and verify the suite would have caught them (run the offending change against the current suite in staging; a miss means a coverage gap to close).
- Mutation check: deliberately introduce small regressions (weaken the injection filter, change a tool name in a prompt, tighten a schema) and confirm the intended canaries go red while unrelated ones stay green.
- Noise measurement: run the suite repeatedly against an unchanged configuration and record the false-red rate; a suite with a nonzero flaky-task rate gets the flaky task fixed or replaced, not ignored.
- Runtime and cost telemetry: per-canary duration and spend, trended, proving the suite stays inside its budget as it evolves.

## Failure modes and correction

- Alert fatigue after a string of Tier 2 diffs leads to reflexive overrides. Correction: track override reasons, surface override rates to leadership, and retune thresholds when the justifications show a threshold is miscalibrated rather than the agent regressed.
- Fixtures age as real tool APIs drift, so canaries pass against a world that no longer exists. Correction: fixture refresh checklist whenever an upstream tool announces breaking changes, plus periodic spot-checks of live behavior against fixture assumptions.
- The suite grows by accretion past its time budget and gets scheduled "for later." Correction: enforce the size budget with mandatory retirement on every addition.
- Deterministic-answer canaries overfit the team into optimizing for them. Correction: keep the deeper corpus and drift checks as the truth source for quality, and treat canary greens as "no known regression," not "good."

## Limitations

A fixed small suite measures known risks only; novel failure modes pass green until they become known. Fixture fidelity is always partial, so environment-dependent regressions (latency-driven timeouts, real retrieval variance) can slip through. Nondeterministic model behavior makes some assertions probabilistic no matter the pinning, forcing tolerance bands that trade sensitivity for stability. And the suite says nothing about aggregate quality trends; it is a smoke detector, not a thermostat.

## Canonical sources

- NIST AI RMF 1.0, AI Risk Management Framework (TEAR function, testing and monitoring): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide: https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-61r2.pdf
- OWASP, LLM Top 10 for LLM Applications: https://genai.owasp.org/llm-top-10/
