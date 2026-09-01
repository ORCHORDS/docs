# Agent LLM-as-Judge Calibration

Teams increasingly score agent outputs with a judge model because human adjudication does not scale. The failure is quiet: an uncalibrated judge drifts, favors its own phrasing, flips verdicts on trivial rewording, and its scores still look plausible weeks after they stopped meaning anything. Calibration treats the judge as a measuring instrument. You establish its accuracy against a labeled adjudication set, quantify bias and variance, set alert thresholds, and re-run the whole exercise whenever the judge, the rubric, or the judged model changes. This article covers building the calibration set, running calibration and drift checks, and acting on the numbers.

## Scope

Applies to teams using an LLM to grade agent outputs or trajectories against a rubric, whether for offline evaluation, online quality sampling, or regression gating. Covers judge prompt design for measurability, labeled set construction, agreement metrics, bias probes, drift monitoring, and judge version pinning. Does not cover choosing the judge vendor, human review-queue design, or statistical uncertainty in aggregate scores, which deserve their own treatment.

## Workflow or implementation guidance

1. Write the rubric as mutually exclusive, observable criteria before touching a judge prompt. "Did the agent cite a source for every factual claim" scores reliably; "was the response good" does not. Each criterion gets a definition, anchors for each score level, and two worked examples, one at each extreme.
2. Build a labeled adjudication set: 150 to 300 cases spanning the agent's task distribution, each independently labeled by at least two humans with disagreements adjudicated by a third. Freeze it, version it, and never let judge outputs into the labels. Include hard cases deliberately; a set of easy cases will flatter any judge.
3. Encode the judge prompt to force structure: per-criterion scores with quoted evidence before each verdict, then an overall decision. Require the judge to quote the exact span it is scoring; this raises agreement and makes audits mechanical. Randomize item order and, where position matters, counterbalance.
4. Run the calibration pass and compute, per criterion: exact agreement, agreement within one level for ordinal scales, and Cohen's kappa (or Krippendorff's alpha for multi-labeler sets) against the human labels. Record a confusion matrix per criterion; kappa near zero on a criterion means the judge is guessing no matter what raw accuracy says, especially on skewed distributions.
5. Probe known biases explicitly: self-preference (judge prefers outputs from the same model family), verbosity preference, position bias in pairwise setups, and leniency drift over long grading runs. Each probe is a targeted fixture set where the confound is the only variable.
6. Set acceptance thresholds before results arrive, in writing: minimum kappa per criterion, maximum bias-probe skew, and a maximum flip rate under paraphrase. A judge that fails a threshold is not shipped, and thresholds are renegotiated only with new evidence, not to rescue a failing run.
7. Pin the judge: model version, prompt hash, temperature (zero or near zero), and decoding parameters recorded with every grading run. Any change to judge or judged agent triggers a mandatory recalibration.
8. Schedule drift checks: weekly or per-release re-runs on a fixed subset, comparing score distributions and per-criterion agreement to the calibration baseline. Alert on shifts beyond thresholds even when aggregate averages look stable; drift often hides in one criterion while the mean barely moves.
9. Keep humans in the loop on a sampled basis: a fixed percentage of production-graded outputs goes to human adjudication, and disagreement patterns feed back into the labeled set as new hard cases.

## Controls

- Versioned judge configuration (model, prompt, parameters) with change review; no anonymous prompt edits.
- Labeled set governance: frozen versions, documented provenance for each case, restricted write access, and a change log.
- Automated calibration harness in CI that blocks judge or agent releases when thresholds fail.
- Paraphrase and order-invariance fixtures run on every judge prompt change, with flip-rate reporting.
- Separation of duties: nobody both tunes the judge prompt and adjudicates the labels for the same criterion.

## Validation evidence

- Calibration report per judge version: per-criterion kappa, confusion matrices, bias-probe results, and paraphrase flip rates, stored with the release it cleared.
- Time series of drift-check metrics with alert annotations, demonstrating the monitor fires on an intentionally introduced change (inject a known-degraded judge prompt in staging to prove detection works).
- Human-sample disagreement logs: monthly comparison of judge versus human on production traffic, with the delta trended.
- Reproducibility evidence: same inputs, same pinned judge, run twice, produces identical or near-identical scores, with any nondeterminism quantified.

## Failure modes and correction

- Judge and agent co-evolve until the judge grades style it was trained on rather than substance; scores rise while quality does not. Correction: refresh labeled sets from real user-reported failures, and rotate judge model families periodically where feasible.
- Labels encode one annotator's idiosyncrasies because adjudication was rushed. Correction: re-adjudicate criteria with low inter-rater agreement among humans; a criterion humans cannot agree on cannot be calibrated and needs redefinition.
- Pairwise grading leaks position bias into release decisions. Correction: always grade both orders and average, or reject items where order flips the verdict, then track the flip rate as its own metric.
- Thresholds get quietly lowered after a bad week. Correction: threshold changes require a written justification and a recalibration run attached.

## Limitations

Calibration bounds a judge's agreement with one labeled distribution; new task types start uncalibrated until new labels exist. Kappa thresholds are guidelines, not physical constants, and very skewed criteria make all agreement metrics hard to interpret. Judges remain vulnerable to confident nonsense in graded outputs, so factual-accuracy criteria benefit from programmatic cross-checks (retrieval grounding tests) alongside judgment. Finally, the labeled set ages: coverage decays as the agent's task mix shifts, so recalibration is a recurring cost, not a one-time gate.

## Canonical sources

- NIST AI 100-2, A Taxonomy and Terminology of Adversarial Machine Learning: https://nvlpubs.nist.gov/nistpubs/ir/2024/NIST.AI.100-2e2023.pdf
- NIST AI Risk Management Framework (AI RMF 1.0): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- Cohen's kappa (original agreement-statistic literature), summarized by NIST/SEMATECH e-Handbook of Statistical Methods: https://www.itl.nist.gov/div898/handbook/
