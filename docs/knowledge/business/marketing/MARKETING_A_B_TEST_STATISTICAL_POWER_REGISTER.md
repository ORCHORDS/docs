# Marketing A/B Test Statistical Power Register

## Scope

This register governs the planning, evaluation, and archiving of statistical power for marketing A/B and multivariate tests. It applies to tests whose outcome drives campaign decisions, creative selection, copy selection, audience allocation, paid spend, bid strategy, landing page selection, email subject selection, push notification selection, and downstream personalization. It applies wherever the team is willing to commit incremental budget, retire a creative, or change a customer-facing message based on the experimental result. It does not apply to one-off decision-making that is not committed to in advance.

The governing reference is ISO 3534-1, which defines the vocabulary of statistics used in disciplines that rely on statistical methods, including the formal treatment of variables, populations, samples, hypotheses, estimators, and the consistency of statistical conclusions. A statistical power register uses the vocabulary of effect, sample, alpha, beta, power, and stopping rule in a consistent way across the team, so that a "winner" declared by one campaign means the same thing as a "winner" declared by another.

## Workflow or implementation guidance

A statistical power register functions as the documented record of decision rules rather than as a calculator. Building one proceeds in six steps.

1. Define a decision criterion in advance. The team writes down the smallest effect that matters operationally (the Minimum Detectable Effect, MDE), the chosen significance level, the desired statistical power (commonly 80%), the unit of randomization (session, user, device, household), the expected conversion rate baseline, the anticipated traffic per day, and the maximum runtime.
2. Compute the sample required and the runtime required. The sample size calculation uses the chosen test statistic, two-sided or one-sided framing, accounting for any baseline variance estimate, and any anticipated clustering or stratification. Runtime is the sample required divided by the expected eligible traffic per day, adjusted for the traffic allocation across variants.
3. Record the design. The register entry identifies the test name, hypothesis, decision rule, sample required, runtime required, eligible population definition, exclusion rules, traffic allocation, randomization unit, the variant whose effect size drives the MDE, and any pre-registered segmentation or sub-population analyses.
4. Run, observe, and stop. The team monitors variants against the decision rule but does not peek at results to declare a winner before the planned sample is reached, except in the case of a separate ethics or safety stop rule. Sequential or Bayesian decision frameworks, when used in place of fixed-horizon testing, are documented and registered as alternative decision criteria.
5. Compute and report. The result is reported with the observed effect size and a confidence interval, the actual sample reached, the decision rule outcome, and any deviations from the design. Failure to reach the planned sample is treated as inconclusive, not as a win.
6. Archive. The closing record, including the registered design and the observed outcomes, is retained alongside the deployed variant and any subsequent analysis.

## Controls

The controls in this register are designed to reduce the risk that a campaign decision is treated as supported when the statistical evidence is weak.

- A test plan is registered before exposure begins; post-hoc "winners" declared without a registered plan are not accepted as the basis for campaign decisions.
- The randomized unit is fixed in advance and not changed after the test starts.
- A "winner" requires either a registered decision rule to have been met at the planned horizon, or a registered Bayesian or sequential rule to have produced a stop signal.
- Pecks, sequential glances, and early stopping for statistical significance are not treated as evidence unless a registered sequential testing protocol is in place.
- Effect sizes are reported with uncertainty (a confidence interval); effects described only as "statistically significant" or "lifted" without interval information are not accepted as primary evidence.
- Multiple-comparison corrections are applied when multiple metrics or segments are inspected; the family-wise error rate chosen is registered.
- Data excluded from analysis (fraud, bots, internal traffic, geo exclusions) is named and the rationale recorded; per-segment analyses are named in the plan rather than discovered post hoc.

## Validation evidence

Evidence is collected for each test and audited periodically.

- A test-plan snapshot at registration: hypothesis, decision rule, MDE, sample required, runtime required, randomization unit, exclusion rules, traffic allocation.
- A pre-launch snapshot confirming that the launched variant and creative are unchanged from the registered plan or are documented as a deliberate deviation.
- A runtime log of exposure per variant, eligibility filtering applied, and any unusual traffic events.
- A closing record with the observed effect size, confidence interval, decision-rule outcome, the deployed variant, and any subsequent variants.
- Periodic audits that compare declared "winners" against their registered plans, including the proportion of tests that actually reached their planned sample.

## Failure modes and correction

Common failures include optimizing for p-values through repeated peeking, treating a 5% lift as a guaranteed effect, declaring a winner from an underpowered test, ignoring the planned budget for variants, declaring winners from a sample that contains ineligible traffic, allocating traffic unequally or unevenly without registering the change, replacing the registered metric after the fact, and continuing a test beyond the planned horizon to chase a result. Other failures include running many metrics without adjusting for multiple comparisons, reporting only the segments that "won," and using auto-optimization tooling that does not preserve a registered decision rule.

Correction begins by treating the underpowered or undeclared result as inconclusive: no campaign decision is based on it. The test plan is then reviewed, the deviation recorded, and a corrected test registered. Re-analysing the result without a registered plan is not acceptable as primary evidence; re-analysis may be used only for hypothesis generation under a separate registered follow-up. Where the failure originated in tooling that does not permit pre-registration, the tooling is replaced or the testing workflow is changed so that registration is the first step.

## Limitations

This register does not adjudicate whether an experiment is the right tool for the decision at hand, whether the chosen decision metric captures the business outcome the team cares about, whether a stop rule accounts for long-tail effects, whether observed effects will replicate, whether the conditions of the test (audience, season, geography) generalize beyond the test window, or whether a winning variant is consistent with all disclosure and substantiation rules. A statistical register produces consistent vocabulary; it does not on its own guarantee a correct inference.

## Canonical sources

- **Primary authority 1 — ISO 3534-1:2006, Statistics — Vocabulary and symbols — Part 1: General statistical terms and terms used in probability:** [https://www.iso.org/standard/76070.html](https://www.iso.org/standard/76070.html)
- **Primary authority 2 — ISO Online Browsing Platform (statistics vocabulary index):** [https://www.iso.org/obp/ui/#iso:std:iso:iec:3534:-1:en](https://www.iso.org/obp/ui/#iso:std:iso:iec:3534:-1:en)
