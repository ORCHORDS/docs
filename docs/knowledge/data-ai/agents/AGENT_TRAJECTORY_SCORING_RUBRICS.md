# Agent Trajectory Scoring Rubrics

Two agents can reach the same correct answer while one wasted eleven tool calls, leaked a user identifier into a third-party service, and nearly executed a destructive command before backing out. Final-answer grading sees none of that. Trajectory scoring evaluates the whole path: which tools were chosen, in what order, with what arguments, what was done when results surprised the agent, and whether the final answer is grounded in what the tools actually returned. Done well it catches process failures that outcome grading systematically misses; done badly it rewards theater. The rubric design and rater checks below keep it in the first category.

## Scope

Applies to evaluation harnesses that score multi-step agent executions, whether from batch test runs, production sampling, or red-team exercises. Covers rubric construction over step-level events, scoring aggregation, inter-rater reliability for human scorers, and evidence requirements. Does not cover LLM-judge calibration methodology, statistical treatment of aggregate eval scores, or canary-suite selection, which are separate articles in this knowledge base.

## Workflow or implementation guidance

1. Define the event schema first. A trajectory is a sequence of typed events: user goal, agent reasoning summary, tool call with name and sanitized arguments, tool result digest with size and status, permission grant or denial, human handoff, and final answer with citations. Without a stable schema, every rubric change silently redefines history.
2. Derive dimensions from failure analysis, not intuition. Mine postmortems and production incidents for recurring process failures, then write one rubric dimension per failure family. Typical dimensions: tool selection appropriateness, argument correctness and minimality, sequencing and dependency handling, recovery from errors or empty results, data handling (did sensitive fields stay inside permitted boundaries), grounding (does the answer cite retrieved evidence), and stopping behavior (did the agent stop when the goal was met or spiral).
3. Score at the step level, then aggregate. Each step gets zero or more dimension findings with severity (compliant, minor, major, critical). Dimension scores roll up per trajectory, and the trajectory record keeps every finding attached to its step so reviewers can audit any aggregate.
4. Anchor every level of every dimension with two or three real examples from your corpus. "Major: called a write tool with arguments derived from unvalidated tool output" is scorable; "did something risky" is not.
5. Decide the delegation rule for critical findings: any critical on data handling or destructive action marks the whole trajectory failed regardless of dimension averages, because averages let one dangerous step hide behind ninety boring ones.
6. Pilot with three or more human raters on the same 30 trajectories. Compute per-dimension inter-rater agreement (percent agreement plus kappa for the ordinal severity levels), resolve disagreements in an adjudication meeting, and revise rubric wording where raters diverged. A dimension that stays unreliable after revision is either two dimensions in disguise or unusable; split or cut it.
7. Automate the mechanical dimensions. Argument minimality, permission-boundary compliance, and grounding citation checks are largely computable from the event schema; reserve human or judge attention for judgment dimensions like recovery quality. Automated checks get fixtures too, with known-good and known-bad trajectories.
8. Version the rubric with its corpus. When the rubric changes, rescore a frozen historical sample so trend lines continue rather than jump, and annotate dashboards at every rubric version boundary.
9. Feed the findings loop: aggregated dimension failure rates drive targeted test additions, and every newly discovered failure mode either maps to an existing dimension or spawns a new one with anchors before it is reused.

## Controls

- Rubric change control: dimensions, anchors, and severity definitions are reviewed artifacts with version numbers and rationales.
- Rater qualification: new raters pass a calibration round against adjudicated trajectories before their scores count.
- Blind scoring: raters see the trajectory only, not the agent version, prompt variant, or team that produced it.
- Sanitization gate: trajectories entering scoring are scrubbed of secrets and minimized for personal data before human eyes see them.
- Sample-integrity control: production-sampled trajectories cannot be cherry-picked out of scoring by the team being scored.

## Validation evidence

- Inter-rater reliability report per rubric version: per-dimension percent agreement and kappa across the pilot set, plus adjudication notes for every disagreement.
- Rubric discrimination check: a set of intentionally degraded trajectories (wrong tool order, argument sloppiness, ungrounded answer) must score strictly worse than clean counterparts on the intended dimensions and only those dimensions.
- Automation fixtures: every programmatic check demonstrated against true-positive and true-negative trajectory fixtures with expected findings enumerated.
- Trend continuity evidence: before-and-after rescoring of the frozen sample at each rubric change, with per-dimension deltas explained.

## Failure modes and correction

- Raters reward verbose reasoning summaries that narrate diligence while the tool calls were wrong. Correction: score from events, treat narrated intent as non-evidence, and add an anchor stating so.
- Trajectories from different task types get averaged together, drowning a dimension that only fires on one task family. Correction: report dimension rates stratified by task type, not only globally.
- Judges or raters drift lenient after weeks of exposure to the same failure patterns. Correction: inject known-bad calibration trajectories at a fixed rate and monitor their scores.
- The event schema silently drops a new event type after an agent framework upgrade, so whole failure classes vanish from view. Correction: schema conformance test that fails when unknown event types appear, plus coverage monitoring.

## Limitations

Trajectory scoring is expensive per case, so coverage trades off against cost; stratified sampling mitigates but does not remove this. Scoring measures observed behavior, not latent risk the task never exercised. Human reliability limits rubric granularity in practice: beyond four or five severity-anchored levels, agreement decays. And because rubrics encode today's known failure modes, novel failure classes score clean until someone notices and writes the dimension, which is why the findings loop is part of the method rather than an afterthought.

## Canonical sources

- NIST AI 100-2, A Taxonomy and Terminology of Adversarial Machine Learning: https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.AI.100-2e2023.pdf
- NIST AI RMF 1.0, AI Risk Management Framework: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST/SEMATECH e-Handbook of Statistical Methods (measurement system analysis): https://www.itl.nist.gov/div898/handbook/
