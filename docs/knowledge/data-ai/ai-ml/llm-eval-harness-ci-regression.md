# llm-eval-harness-ci-regression

**Issue:** LLM applications change behavior when prompts, models, retrieval corpora, or tool definitions change — none of which conventional unit tests catch, because the output is non-deterministic natural language rather than an assertable value. Teams that lack a continuous evaluation harness discover regressions from users weeks after shipping them. The engineering problem is building an offline eval harness that runs on every pull request, gates merges with statistical thresholds instead of exact-match assertions, versions golden datasets alongside prompts, and feeds production traces back into the eval set so the suite evolves with real traffic. 2025-2026 practice converges on treating prompts and eval datasets as versioned code artifacts with CI gates, batch-mode regression runs against golden datasets, and live-mode monitoring for drift.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core harness design

1. **Golden dataset as the foundation.** Maintain a versioned set of curated test cases (input, ideal output or rubric, metadata tags) covering your critical user intents. Store it in the repo next to the prompts it tests so any prompt change necessarily travels with an eval change, and review dataset diffs in code review exactly like code.

2. **Layered scoring strategy.** Combine three scorer types per case: deterministic checks (regex, JSON schema validation, exact strings) for machine-checkable invariants; reference-based metrics (similarity to gold answers, faithfulness, citation accuracy) for open-ended outputs; and LLM-as-judge with a fixed rubric for qualitative dimensions. Never rely on a single judge score alone — deterministic assertions anchor the flaky top layer.

3. **Deterministic harness plumbing.** Pin everything the model does not control: model version and provider, temperature (usually 0 or a fixed low value), seed where supported, retrieval snapshot, and tool mocks. The harness should differ from the last run only through the change under test; any other variance is noise you designed in.

4. **Framework choice matters less than lock-in avoidance.** promptfoo, Braintrust, OpenAI Evals, LangSmith, and self-written harnesses all reduce to the same loop over dataset x prompt x scorer. Keep datasets and scorers as plain files/functions outside the framework so migrating tools does not orphan your eval corpus.

## CI gating and regression strategy

1. **Run evals as a required check.** Wire the harness into CI (GitHub Actions or equivalent) triggered on prompt, model-config, and retrieval-pipeline changes. The check fails when aggregate scores drop beyond a configured threshold versus the main-branch baseline, not on single-case deltas — that is the merge signal teams actually trust.

2. **Report score deltas, not just pass/fail.** Emit a table of per-category scores (this prompt version vs baseline, with confidence intervals) as CI output or a bot comment. Reviewers act on "faithfulness dropped 6 points on multi-hop queries" immediately; they ignore "eval failed."

3. **Baseline against main, not against perfection.** Store the last-known-good score for each metric and dataset slice. The question CI answers is "did this change make things worse," which requires a stored baseline and two-sided comparison, not an absolute quality bar that moves with every model upgrade.

4. **Tier your gates by risk.** Cheap smoke suites (tens of cases, deterministic assertions) run on every PR; full regression suites (hundreds of cases, judges) run nightly and pre-release. This keeps PR feedback inside a few minutes instead of a half hour.

## Handling non-determinism

1. **Fixed sampling parameters first.** Temperature 0, fixed seeds, and pinned model snapshots eliminate most variance before you need statistics. Judge models need the same treatment — a judge sampled at temperature 1 turns a stable system into noise.

2. **Thresholds over exact matches.** Because outputs vary run to run, gate on aggregate metrics with tolerance bands (for example, fail only if score drops more than 2 points with p under 0.05). Compute significance with multiple runs per case on small suites; on large suites the aggregate is usually stable enough for simple deltas.

3. **Quarantine flaky cases.** Track per-case variance across runs. Cases whose scores swing widely get flagged, investigated, and either rewritten with a sharper rubric or excluded from gating while remaining visible in reports — the same flaky-test hygiene classic CI taught us.

4. **Judge calibration spot checks.** Sample a few percent of judge decisions for human review each week and log agreement. A judge that silently drifts (often after a provider model update) corrupts every gate downstream, so judge quality needs its own metric.

## Dataset management and drift

1. **Mine production traces.** Continuously sample real traffic (especially failures and low-rated responses), anonymize, and promote representative cases into the golden dataset. A static dataset tests last quarter's product; the flywheel keeps CI honest about current usage.

2. **Slice by intent, not just aggregate.** Tag cases by query type, difficulty, language, and feature area, and gate per slice. Aggregate scores hide category collapses — a merge that gains 3 points on easy FAQs while losing 20 on multi-step reasoning looks green in aggregate.

3. **Version datasets with semantic bumps.** Treat dataset changes like API changes: adding cases is minor, changing gold answers or rubrics is major and requires re-baselining. Record which dataset version produced each stored baseline or comparisons become meaningless.

4. **Watch for distribution drift in live mode.** Pair the offline harness with online monitoring of the same metrics computed over sampled production traffic. When live scores diverge from offline scores, the product has drifted from the dataset — that divergence, not the absolute score, is the trigger to invest in fresh data.
