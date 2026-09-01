# Customer Success Survey Question Bank Governance

CSAT and NPS programs run on question banks — the curated sets of items, scales, and follow-up prompts that surveys draw from. Over time these banks decay: a word is tweaked to sound friendlier, a scale point is reworded, one item quietly replaces another, and the trend line silently stops meaning what it meant. Meanwhile response rates fall, and the shrinking respondent pool becomes a biased sample treated as a census. This article governs question banks: versioned wording, sampling plans, and bias controls that keep survey findings defensible.

## Scope

Applies to standardized customer-satisfaction and loyalty instruments used in customer-success measurement — transactional CSAT after resolved cases, relationship NPS at intervals, and periodic relationship surveys drawn from a governed bank. Covers item lifecycle, sampling design, nonresponse handling, and reporting discipline. Does not cover bespoke qualitative research, usability studies, or regulated clinical or patient-satisfaction instruments, which follow their own methodological authorities. Where survey results are quoted to customers or in public claims, advertising-substantiation and truthfulness obligations apply on top of this governance.

## Workflow or implementation guidance

1. **Version every item.** Each bank entry carries an identifier, exact wording, scale definition (points, labels, endpoints), placement context, effective date, and retirement date. A trend computed across a wording change is annotated with the change, or computed only within the stable segment — never spliced silently.
2. **Route all wording changes through review.** Anyone may propose a rewording; the change record states the reason, the expected effect, and a pre-declared decision on whether the trend continues, resets, or runs in parallel for a validation period. Parallel running — old and new item alternated across equivalent samples — is the preferred method when the trend matters.
3. **Retire and add deliberately.** New items enter through a pilot that checks comprehension (respondents understand the question as intended) before promotion into the production bank. Retired items stay in the catalog with their history so old reports remain interpretable.
4. **Define the sampling plan before fielding.** For relationship surveys, specify the population, the frame, the draw method, the target sample size, and the analysis cut-offs. Stratify by account size and segment so a handful of large accounts cannot dominate an aggregate score. For transactional CSAT, define the trigger, any suppression windows (no survey within N days of a prior one), and deduplication so one customer's bad afternoon does not become five data points.
5. **Instrument for nonresponse.** Record invitations sent, deliveries, and completions by stratum. Monitor the response rate itself as a metric; a falling rate is a data-quality event, not a background condition to shrug at.
6. **Assess and adjust for response bias.** Compare respondents to nonrespondents on observable characteristics — tenure, support volume, product tier — and report the differences. Where bias is material, report adjusted estimates alongside raw ones, and say which is which.
7. **Standardize the follow-up prompt.** Open-text follow-ups ("what is the primary reason for your score?") keep identical wording across waves; spontaneous wording variation by survey owner is treated like any other item change.
8. **Publish the methodology with the number.** Any reported CSAT or NPS figure carries its sample size, response rate, fielding window, and item version. A score without its methodology is a decoration.

## Controls

- Only bank-listed items may be fielded; ad-hoc edits in the survey tool are a control failure detected by periodic tool-to-bank reconciliation.
- Sampling suppression rules protect customers from over-surveying: frequency caps per contact and per account, with a total-survey-load ceiling.
- Open-text responses containing personal or sensitive information are minimized at intake into reporting; quotes used externally are paraphrased or de-identified unless consent covers attribution.
- Declining response rates below a defined floor trigger a mandatory methodology review before the next wave, not just a note in the appendix.
- Segmented reporting is the default; grand-mean scores that hide a bimodal distribution require the distribution to be shown.

## Validation evidence

Evidence of a governed bank: the item catalog with version histories; change records with reasons and trend-disposition decisions; pilot results for items promoted during the period; the sampling plan per wave with realized sample sizes and response rates by stratum; respondent-versus-nonrespondent comparisons on observables; tool-to-bank reconciliation output confirming no unauthorized wording; and at least one parallel-run validation where a wording change occurred. Reproduce one published figure from raw response data to the reported value.

## Failure modes and correction

- **Silent wording drift** detected in reconciliation: re-field the drifted item correctly, annotate affected trend segments, and review tool permissions that allowed the edit.
- **Collapsing response rate** masked by absolute counts (fewer invites, same completions): recompute rates, treat as a data-quality incident, and shorten or re-target the instrument before the next wave.
- **Promoter-skewed sampling** (only recent case-contacted customers invited): rebuild the frame from the full relationship population and re-baseline the score with the wave change annotated.
- **Scale-point relabeling** mid-trend: reset the trend, run the old labels in parallel for one cycle, and document the discontinuity in every report touching the series.

## Limitations

Survey measures self-reported perception, not behavior or value delivered; they complement telemetry and renewal outcomes without replacing them. Response bias can be bounded and disclosed but not eliminated, and low-incidence populations may never support statistically comfortable samples — reporting should say so plainly. Wording governance also cannot make two organizations' scores comparable; benchmarking across vendors inherits every difference in methodology.

## Canonical sources

- [FTC, Deception Policy Statement and advertising substantiation guidance](https://www.ftc.gov/legal-library/browse/ads-legal-resources) — truthfulness and substantiation when survey results support external claims.
- [NIST, Engineering Statistics Handbook, Section 7: Process Measurement](https://www.itl.nist.gov/div898/handbook/pmc/pmc.htm) — measurement system discipline and sampling considerations.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
