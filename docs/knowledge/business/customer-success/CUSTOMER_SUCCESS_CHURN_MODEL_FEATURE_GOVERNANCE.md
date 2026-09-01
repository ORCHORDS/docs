# Customer Success Churn-Model Feature Governance

A churn model promises to flag accounts likely not to renew before the loss is certain. Its predictions steer scarce retention effort, so the features feeding it carry real power: a feature that leaks post-hoc information inflates apparent accuracy, and a feature that encodes customer segment can systematically deprioritize whole groups. This article governs the lifecycle of churn-model features — proposal, leakage review, fairness screening, and approval — with production use gated on documented sign-off.

## Scope

Applies to supervised models predicting churn, downgrade, or renewal likelihood in customer-success contexts, and specifically to the feature set: candidate variables, transformations, aggregates, and derived flags. Covers feature admission, periodic review, and retirement. Does not cover model architecture selection or hyperparameter tuning (analytical concerns), nor automated decision-making about individual customers where such use triggers separate automated-decision governance or legal review. Where predictions influence pricing, service levels, or contract terms offered to a customer, this article's controls are necessary but not sufficient — commercial and legal review also applies.

## Workflow or implementation guidance

1. **Register every candidate feature.** No variable enters experimentation without a registry entry: name, business rationale, source system, computation window, availability timestamp, and the earliest moment the value would have been knowable at prediction time.
2. **Run the leakage triage.** For each feature ask: is the value determined before, at, or after the prediction moment? Features whose computation window overlaps the outcome window (for example, usage measured through the end of a quarter used to predict churn in that quarter) are rejected or re-windowed. Indirect leakage — features that proxy the label, such as "cancellation page visits after the renewal date" — receive the same scrutiny.
3. **Document the causal story.** Each surviving feature carries a one-paragraph rationale for why it plausibly influences churn rather than merely correlating with it. Features admitted purely on correlation strength are flagged as such and capped in number.
4. **Screen for proxy discrimination.** Test whether any feature or combination disproportionately concentrates risk scores within protected or vulnerable segments — small-business tenants, education customers, accessibility-dependent users, region, or language. High-concentration features must be justified by legitimate necessity or removed.
5. **Freeze a validation protocol before scoring.** Define the backtest design (time-split, not random-split; out-of-time validation for seasonality), the metrics, and acceptance thresholds before results are observed. Changing thresholds after seeing scores is a governance failure, not iteration.
6. **Approve in writing for production use.** A named approver outside the modeling team signs the feature manifest, validation results, leakage findings, and fairness screen. Production scoring systems load only manifest-listed features.
7. **Review on a schedule and on drift.** Re-examine the feature set at least semiannually and whenever input systems change, definitions drift, or predictive performance decays. Retire features whose predictive value has evaporated rather than letting dead variables accumulate unreviewed.

## Controls

- Segregation of duties: the analyst proposing features cannot be the sole reviewer of leakage or fairness findings.
- The feature manifest is the whitelist; scoring jobs that reference unlisted inputs fail closed and alert.
- Time-based data splitting is mandatory; random splits are prohibited for churn backtests because they leak temporal structure.
- Model cards or equivalent documentation record intended use, excluded uses, known weaknesses, and the populations where performance is weaker.
- Prediction access is restricted to retention decision support; using churn scores to justify differential service degradation for already-struggling customers is a prohibited use recorded in the manifest.

## Validation evidence

A governed model demonstrates: the feature registry with availability timestamps; the leakage triage record showing each feature's determination with reviewer identity; out-of-time validation results against the pre-registered protocol; the fairness screen output with concentration metrics by segment and disposition of flagged features; the signed production approval naming approver and date; and the most recent periodic review showing feature-level performance and any retirements. Reproducibility evidence — the ability to regenerate the validation numbers from versioned code and data — closes the loop.

## Failure modes and correction

- **Leakage discovered post-launch** (inflated accuracy, suspiciously confident scores): suspend production scoring, quantify how many interventions were mis-aimed, re-run validation with corrected windows, and require fresh approval before resuming.
- **Fairness regression after retraining**: roll back to the last approved manifest and open a formal review; do not ship the degraded variant while investigations proceed.
- **Feature-definition drift** (upstream telemetry definition changed, feature silently transformed): align to the versioned definition catalog, annotate the break in performance history, and re-baseline thresholds.
- **Threshold shopping** (acceptance criteria adjusted to fit results): void the approval, re-register the protocol, and repeat validation; record the attempt in governance minutes.

## Limitations

Churn models learn from historical renewal outcomes and inherit whatever bias those outcomes contained. Small tenants and rare churn causes are underrepresented, so per-segment confidence is genuinely lower. Correlation-based features can remain fragile when market conditions shift. Governance reduces the risk of misleading models; it cannot make a noisy signal certain, and predictions should inform — never replace — human judgment in retention conversations.

## Canonical sources

- [NIST AI Risk Management Framework (AI RMF 1.0)](https://www.nist.gov/itl/ai-risk-management-framework) — risk governance, validation, and documentation discipline for predictive models.
- [FTC Business Blog — Keep your AI claims in check](https://www.ftc.gov/business-guidance/blog/2023/02/keep-your-ai-claims-check) — truthful representation of automated model capabilities and limitations.

Local procedures should track the edition in force and be reviewed when the authority replaces it.
