# Customer Success Health Score Weighting Review

A health score compresses many signals — product usage, support experience, sentiment, relationship coverage — into one number that drives intervention priorities. The compression is only as trustworthy as its weights, and weights tend to ossify: set once by intuition, defended thereafter by habit. This article governs the periodic review of health-score inputs and weights, anchored in whether the score actually correlates with the outcomes it is supposed to predict.

## Scope

Applies to composite customer health scores used in customer-success prioritization, renewal forecasting, and escalation triggers. Covers the review of input selection, weight assignment, banding thresholds, and outcome correlation. Does not cover the underlying data quality of individual inputs (governed by telemetry source authority and joined-view controls), model-based churn prediction with learned coefficients (governed separately as churn-model feature governance), or contractual service-level metrics, which are defined by agreement rather than by internal design.

## Workflow or implementation guidance

1. **Publish the current recipe.** Before any review, the score's definition is documented: each input, its source and definition version, transformation, weight, banding thresholds, and refresh cadence. A score that cannot be fully specified cannot be reviewed — it can only be argued about.
2. **Schedule the review on outcome cadence, not calendar convenience.** Reviews align with renewal cycles so that enough outcome data (renewed, expanded, churned, downgraded) exists per band to evaluate the score meaningfully; an annual review with quarterly renewals wastes signal.
3. **Measure correlation before discussing weights.** The review opens with the evidence: outcome distribution by health band, lead time between band movement and outcome, and score stability. A score whose red band churns at the same rate as its green band has failed regardless of how sensible its weights look.
4. **Examine each input's marginal contribution.** For every input, test whether it adds predictive separation beyond the others — an input whose contribution is redundant with usage, or which moves nothing, is a candidate for removal, not re-weighting. Conversely, inputs with unexplained volatility may be noise-dominated.
5. **Adjust weights against documented rationale.** Weight changes state the observed evidence motivating them, the expected effect on band populations, and the proportionality of accounts that will shift bands. Sweeping recalibration that moves a third of the portfolio between bands is treated as a re-design requiring fresh validation, not a tuning pass.
6. **Guard against self-fulfillment.** Inputs that measure intervention intensity (escalations opened, save attempts) rather than customer state can make the score predict effort rather than risk. Separate state-like inputs from action-like inputs, and flag action-like inputs for removal or reclassification.
7. **Keep segment comparability deliberate.** Weights may legitimately differ by segment — enterprise and small-business health rarely decomposes identically. Where segment-specific recipes exist, each is reviewed with its own outcome correlation, and cross-segment comparisons carry the recipe difference as a caveat.
8. **Version and annotate.** Every accepted change increments the score version; trend charts spanning versions show the annotation. Band-level history is preserved so pre- and post-change populations are auditable.

## Controls

- Changes to weights or thresholds require approval from a reviewer outside the team that owns the score's operational consequences.
- No input enters the score without a declared authoritative source and definition version; inputs from undesignated sources are barred.
- Minimum sample thresholds per band and segment govern what may be concluded: below the threshold, findings are labeled exploratory and drive no changes.
- The score's gaming surface is reviewed — if account teams can materially move the score through discretionary actions, those actions are identified and the input bounded or removed.
- Downstream consumers (forecasting, staffing) are notified of version changes with band-population impact before activation, not after.

## Validation evidence

Each review produces: the versioned recipe in force entering review; outcome-by-band tables with sample sizes and confidence treatment; per-input marginal contribution results; the proposed change record with rationale and projected band movement; the approval record; and post-change monitoring showing band populations against projection for at least one full cycle. The standing test of the score remains simple and relentless: rank correlation between score at a fixed lead time before renewal and realized outcome, per segment, per version.

## Failure modes and correction

- **Overfit to the last cycle** (weights tuned so tightly to recent outcomes that the next cycle diverges): constrain changes, prefer removing noise inputs over precision re-weighting, and hold out data — validate on renewals not used to motivate the change.
- **Zombie inputs** (components retained because they were always there): the marginal-contribution test forces removal or evidence-based retention each cycle.
- **Segment blindness** (one recipe applied to structurally different segments): detected when correlation holds overall but inverts within a segment; fix by segment recipes or explicit caveats.
- **Version splice misreading** (trend charts mixing versions): enforce version annotations on all longitudinal reporting; re-baseline the trend after major versions.

## Limitations

Correlation evidence is observational: health scores predict, they do not prove, and interventions themselves alter outcomes in ways that muddy the measurement. Small segments may never support stable weight estimation, accepting coarser scores as the honest price of small data. A one-number summary will always discard context that a human reviewer should see alongside it, and the score should trigger judgment, never replace it.

## Canonical sources

- [NIST, Engineering Statistics Handbook, Section 1: Measurement and Process Characterization](https://www.itl.nist.gov/div898/handbook/mpc/mpc.htm) — measurement system characterization and stability discipline.
- [ISO 9001 Quality management](https://www.iso.org/iso-9001-quality-management.html) — evidence-based review, documented information, and improvement-cycle structure.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
