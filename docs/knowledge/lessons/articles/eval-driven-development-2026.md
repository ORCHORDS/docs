# eval-driven-development-2026

**Issue:** LLM team ships prompt changes weekly. Two months in, nobody can tell whether the new prompt is better than the old one. Quality regressions are caught by angry users, not by CI.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

"Eval-driven development" gets said a lot. In practice, three failure modes show up:

1. **No golden set.** Prompts are tweaked based on vibes, demos, and a few cherry-picked examples. There is no fixed test set; every prompt change re-litigates the same edge cases.
2. **Annotators disagree silently.** Two experts label the same example differently. The metric on the golden set is unstable, so the eval bar is meaningless.
3. **In-place edits.** Someone fixes one bad label in the eval JSONL. The next run produces a different number than the last run. Historical trend is broken.

The eval set is the test suite. Treat it like code, not like a wiki.

## The golden set protocol

An eval-driven pipeline is:

```
production traffic → sample → label (two humans) → adjudicate → golden.jsonl
                                                                  ↓
                                                          frozen, versioned
                                                                  ↓
candidate prompt → run on golden.jsonl → rubric score → compare to baseline
```

The eval set is a hand-curated set of inputs with verified correct outputs, drawn from real production traffic, not invented. Sampling is the hard part. Most teams sample too few edge cases. The discipline:

- **Source from real production traffic.** Mine support tickets, search logs, escalation cases, user feedback. Do not invent inputs from imagination.
- **Sample the failure modes.** Adversarial inputs, multi-turn edge cases, ambiguous cases where the wrong answer is plausible. If your eval set is all happy-path, your metric is meaningless.
- **20-50 examples for early stage.** Anthropic's recommendation for first-pass evaluation. Below 20, statistical noise dominates. Above 50, annotation cost starts to bite.
- **500-1000 for mature systems.** Split 50/50 validation/test. The judge LLM is tuned on validation; final report uses test.

The golden set is **immutable in place**. Every change is a new file: `golden_v1.jsonl`, `golden_v2.jsonl`. Track the diff. Historical metrics are broken otherwise.

## The two-annotator agreement rule

Inter-annotator agreement (IAA) is the ceiling on any model eval. If two domain experts agree 75% of the time on the same example, no model can score higher than 75% and be trusted. The metric is a property of the rubric, not the model.

The standard protocol:

- 5-15% of items get 2-3 annotations, specifically for IAA monitoring
- The remaining 85-95% get single annotation for cost efficiency
- Compute IAA on rolling windows (last 1000, last week, last batch)
- Alert on drops below threshold

The right metric for the task:

- **Cohen's kappa** — two annotators, categorical labels
- **Fleiss kappa** — three-plus annotators, categorical
- **Krippendorff's alpha** — production scale, handles missing data
- **Bradley-Terry** — preference data, pairwise ranking

The right target band, calibrated to task subjectivity:

| Subtask | Target kappa |
|---|---|
| Objective (extraction, routing, classification) | ≥ 0.90 |
| Moderately subjective (summarization, tone) | 0.70-0.85 |
| Inherently subjective (style, opinion) | 0.60-0.75 |

If kappa is below the band, the rubric is broken, not the annotators. Rewrite the rubric. Add worked examples for borderline cases. Re-annotate. Below 0.4, treat the label as unreliable; don't ship model scores derived from it.

## The adjudication rule

Disagreements between annotators are a feature, not a bug. They expose rubric ambiguity. The process:

1. Compute per-label kappa, not just overall. Aggregate 0.65 can hide a category sitting at 0.30.
2. Pull every disagreement into a review queue. Don't keep whichever label the majority chose; keep the disputed cases.
3. Adjudicate with a pre-agreed rule: majority vote across 3+ raters, a senior reviewer as tie-breaker, or a synchronous discussion to consensus. Decide the rule before seeing the cases.
4. Log the "why" for every adjudicated case as an addendum to the labeling guide. A future annotator, or a future you, needs the reasoning.
5. Revise the guideline, then re-annotate a fresh sample. Never re-annotate the same examples you just adjudicated.
6. Re-measure agreement; freeze the golden set only once it stabilizes at or above the target band.

When disagreement is genuine (not a guideline gap), the options are: split the label into two clearer categories, allow soft ground truth (a distribution of valid labels with partial credit), or cap the model target at the empirical human agreement ceiling.

## The eval-driven dev loop

Concrete day-to-day:

1. Pick a real failure case from the last week. Add it to the next eval set revision as `golden_v2.jsonl`.
2. Write a new rubric criterion the failure case would fail. This is the regression target.
3. Run baseline prompt against `golden_v2.jsonl`. Record score.
4. Iterate on prompt. Each iteration: run on `golden_v2.jsonl`. Track which criteria improved, which regressed.
5. When the score stops improving, freeze the prompt. Re-validate against `golden_v1.jsonl` to confirm no regression on the original set.
6. Promote to shadow. Run shadow against production traffic. After 24-72h, compare rubric distributions to baseline.

This loop is what makes "prompt engineering" engineering. Without it, prompt changes are vibes-driven.

## The LLM-as-judge calibration

Once the human-labeled set is stable, the judge LLM is calibrated against it. The judge prompt is tuned until its agreement with the human panel exceeds a threshold (typically 0.85+ accuracy, or kappa ≥ 0.7 against the human panel). The judge is then used at scale on unlabeled traffic to track quality.

The split:

- 500-1000 human-labeled examples: judge LLM training and evaluation
- Continuous judge LLM scoring on unlabeled production traffic: trend monitoring
- Periodic re-labeling (10% spot-check weekly): judge drift detection

If the judge and humans disagree on a held-out set, the judge is broken. Don't ship it. The judge inherits the same ceiling a human panel does.

## Verification

The tell that eval-driven dev is working:

- Two engineers independently changing the same prompt reach the same eval score within 0.5 points
- Every prompt PR shows a diff against `golden_vN.jsonl` scores, not a hand-wave
- The model never scores higher on the eval than the human panel would on the same examples

The tell it isn't:

- Eval set edited in place; historical numbers don't match between runs
- Annotator agreement never measured
- Judge LLM accuracy never validated against humans

## Gotchas

- **Sample from production, not imagination.** Invented examples miss the actual failure distribution. Mine logs.
- **Don't edit `golden.jsonl` in place.** Version it. Diff it. Cite the version in every eval report.
- **Compute per-label kappa, not just overall.** A 0.65 aggregate can hide a 0.30 category.
- **The judge inherits the human ceiling.** If your two experts agree 78% of the time, the model target is 78%, not 95%.
- **20 cases is a starting point, not a target.** Mature systems need 500-1000. Below 50, statistical noise dominates.
- **Don't reuse adjudicated cases for re-annotation.** It flatters the new rules. Pull a fresh sample.

## Related

- `patterns/agent-eval-2026.md` — running the eval harness
- `lessons/llm-as-judge-calibration-2026.md` — calibrating the judge LLM
- `lessons/ai-rollout-strategy-2026.md` — using the eval set in the canary gate
- `lessons/agent-failure-modes-2026.md` — what the eval set catches

## Source URLs (verified 2026-08-10)

- https://datavlab.ai/post/inter-annotator-agreement-llm-evaluation-guide
- https://dev.to/ritwikareddykancharla/building-an-llm-evaluation-framework-that-actually-works-4585
- https://ai-de.net/insights/decisions/llm-evaluation-framework-001-labeling-protocol
- https://mlops.community/llm-evaluation-practical-tips-at-booking-com
- https://www.pmsynapse.in/blog/ground-truth-disagreement-annotator-agreement
- https://agileleadershipdayindia.org/blogs/ai-evals-engineer-discipline-hub/golden-dataset-creation-llm-evaluation.html
- https://pmc.ncbi.nlm.nih.gov/articles/PMC12993880/
