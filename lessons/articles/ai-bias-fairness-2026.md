# ai-bias-fairness-2026

**Issue:** Loan approval model denies 40% of applications from one demographic group and 25% from another. EU AI Act Article 10 requires this to be measured, documented, and mitigated before deployment. Compliance deadline: 2 August 2026 for high-risk systems.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

A model that scores 92% overall accuracy can be 88% accurate for one demographic and 96% accurate for another. Aggregate metrics hide this. The EU AI Act treats that as a compliance breach, not a quality issue: fines up to €15M or 3% of worldwide annual turnover under Article 99(4).

## Root cause

Three structural sources of bias in production AI:

1. **Training data bias** — historical data reflects historical discrimination. A credit model trained on past lending decisions learns past discrimination.
2. **Proxy variables** — postcode proxies race, name proxies gender, device ID proxies income. The protected attribute is removed; the proxy is not.
3. **Annotation bias** — labelers' implicit biases get encoded in the labels. Inter-annotator agreement on subjective tasks drops precisely because annotators bring different priors.

Aggregate accuracy cannot detect any of these. The four-fifths rule (ratio ≥ 0.8) is a starting guideline, not a sufficient metric.

## The four metrics that matter

The EU AI Act does not prescribe a specific fairness metric. It requires that one is chosen, justified, documented, and measured. The four candidates:

| Metric | What it ensures | When to use | Limitation |
|---|---|---|---|
| Demographic parity (statistical parity) | Same probability of positive outcome across groups | When historical disparities are themselves a consequence of past discrimination (credit, hiring) | Ignores base rate differences |
| Equalized odds | Equal TPR and FPR across groups | High-stakes decisions where both FP and FN matter (recruitment, medical diagnosis) | Cannot be achieved simultaneously with demographic parity unless base rates are equal |
| Equal opportunity | Equal TPR across groups | When qualified individuals from all groups should be equally likely to be predicted positive | Allows FPR differences |
| Counterfactual fairness | Predictions unchanged if demographic attribute changed | Causal reasoning for high-stakes individual decisions | Trade-off with predictive performance |

For most regulated use cases, demographic parity and equalized odds are the starting pair. The choice depends on the decision context. ISO/IEC TR 24027 lists these four as the standard candidates and recommends selection based on context.

## The three-stage mitigation pipeline

Bias mitigation has three stages, each at a different point in the ML lifecycle:

**Pre-processing (data):**

- Reweighting under-represented groups
- Resampling (oversample minority, undersample majority)
- Suppressing protected attributes and their proxies (postcode, name, device ID)
- Disparate impact remover (Feldman et al. 2015) to reduce feature correlation with protected attributes

**In-processing (training):**

- Fairness constraints added to the optimization objective (e.g., demographic parity difference ≤ 0.1)
- Adversarial debiasing (a second model predicts sensitive attributes; main model is penalized for enabling that prediction)
- Reductions approach (Agarwal et al. 2018): fairness as constrained optimization

**Post-processing (outputs):**

- Threshold adjustment — different classification thresholds per group to achieve equalized odds
- Calibrated equalized odds (Pleiss et al. 2017)
- Reject option classification — abstain in the uncertainty boundary near the threshold

The order of application matters. Pre-processing sets the data foundation; in-processing shapes the model; post-processing adjusts the output. Skipping a stage leaves bias in the layer that wasn't touched.

## The Article 10 data governance checklist

EU AI Act Article 10 is the primary data governance requirement for high-risk AI. Mandatory for any system in employment, credit, education, law enforcement, healthcare, biometric ID, or critical infrastructure:

- [ ] Training, validation, and testing data subject to appropriate data governance and management practices
- [ ] Data is relevant, representative, and free of errors to the extent possible
- [ ] Data has appropriate statistical properties with regard to the persons or groups the system is intended for
- [ ] Data takes into account characteristics of the geographical, behavioral, or functional setting
- [ ] Possible biases examined, identified, and documented
- [ ] Special-category personal data processed only as strictly necessary for bias detection and correction, with safeguards (DPIA, access controls, deletion after use)

The narrow Article 10(5) exception allows processing of race, ethnicity, health, and sexual orientation data for bias monitoring — but only with documented safeguards. This is a compliance permission, not a license.

## The continuous fairness governance programme

Bias monitoring is not a one-time audit. The recommended operational cadence:

1. **Define scope.** Which AI systems are in scope? Prioritize by impact on individuals and EU AI Act risk classification.
2. **Select fairness metrics.** Choose with legal, ethics, and product teams. Document the trade-offs and get sign-off.
3. **Conduct training data audit.** Per Article 10 — representativeness, proxy variables, label quality.
4. **Run pre-deployment bias tests.** Compute fairness metrics on held-out test set segmented by demographic. Document results.
5. **Implement monitoring.** Track fairness metrics in production at minimum quarterly. Set alert thresholds.
6. **Complete FRIA.** Article 27 requires high-risk deployers to conduct a Fundamental Rights Impact Assessment before deploying.
7. **Establish incident response.** What happens when a bias spike is detected? Who is notified? How is the model rolled back or adjusted?
8. **Third-party audit.** Annual independent bias audit by an external assessor, especially before major model releases.

The mistake to avoid: pre-deployment bias test only. Models drift; data drifts; the world changes. A test that passed in January can fail in June because the user population shifted.

## The four-fifths rule and its limits

The "four-fifths rule" (ratio of positive outcomes for protected group vs. advantaged group ≥ 0.8) is a starting guideline from US Equal Employment Opportunity Commission practice. It applies to selection rates. A 0.8 ratio means the protected group's selection rate is at least 80% of the advantaged group's.

The rule is a screening tool, not a fairness proof. A model can pass 4/5 and still fail equalized odds; it can pass 4/5 and still encode proxy discrimination; it can fail 4/5 for a legitimate reason (e.g., differences in qualifications) that has nothing to do with the protected attribute. Use 4/5 as a sanity check, not the bar.

## The intersectional testing pattern

Most bias testing happens on single protected attributes (gender, race, age). The real risk is intersectional: women of color, elderly disabled, low-income minority. A model that passes demographic parity overall can fail intersectionally on a 2D slice.

The pattern: create subgroup partitions for all meaningful combinations of protected attributes in scope (gender × race × age, etc.). Test fairness metrics for each subgroup. The sample size per subgroup will be small; use exact tests or Bayesian methods, not chi-squared.

## Verification

The tell that bias/fairness work landed:

- The model card documents which fairness metric was used, why, and the measured value
- The pre-deployment bias test report is in the Annex IV technical file
- Production monitoring tracks fairness metrics on a quarterly cadence with alerting
- An independent third-party audit has been completed and the report is on file
- FRIA was completed before deployment for any high-risk system

The tell it didn't:

- "We're fair because the model is accurate" — accuracy is not fairness
- Bias was tested once, pre-deployment, and never re-measured
- The training data was not audited for proxy variables
- The team cannot name which fairness metric they targeted and why

## Gotchas

- **Accuracy is not fairness.** A 95%-accurate model can be 80% accurate for one demographic and 99% for another. Aggregate metrics hide this.
- **Proxy variables encode the protected attribute.** Removing "race" from the feature set while keeping "postcode" changes nothing.
- **The four-fifths rule is a screening tool, not a fairness proof.** It can pass on a model that fails equalized odds; it can fail for legitimate reasons.
- **Single-attribute fairness testing misses intersectional harm.** Test on combined attributes.
- **Pre-deployment testing is not enough.** Production drift, user population shift, and data drift all break a model that was fair on day one.
- **Article 10(5) is a permission, not a license.** Processing special-category data for bias detection requires documented safeguards.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — the full EU AI Act structure
- `lessons/ai-explainability-2026.md` — explainability methods often overlap with fairness
- `lessons/agent-guardrails-2026.md` — runtime fairness checks

## Source URLs (verified 2026-08-10)

- https://zylos.ai/research/2026-02-05-ai-bias-fairness/
- https://www.openlayer.com/blog/post/ai-fairness-metrics-guide-enterprise-ml-teams
- https://confir.eu/ai-risks/bias
- https://actproof.ai/blog/bias-monitoring-fairness-testing-eu-ai-act.html
- https://acpr.banque-france.fr/system/files/2026-07/20260701_fairness_discussion_paper_EN.pdf
- https://app-lab.ai/blog/ai-bias-detection-mitigation/
- https://aisecurityandsafety.org/en/guides/demographic-parity-guide/
- https://nocodelisted.com/blog/ai-fairness-bias-audit-guide-eu-ai-act
