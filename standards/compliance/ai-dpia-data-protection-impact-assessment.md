# Data Protection Impact Assessment (DPIA) for AI Systems

> When: Required under GDPR Article 35 whenever processing is "likely to
> result in a high risk to the rights and freedoms of natural persons." In
> 2026, with the EU AI Act overlapping GDPR, DPIAs are effectively mandatory
> for most AI projects that process personal data.
> Who: Data controllers (and processors acting on their behalf) deploying AI
> systems that involve personal data, profiling, automated decision-making,
> large-scale sensitive data, or systematic monitoring.

## When a DPIA Is Mandatory

GDPR Article 35(3) requires a DPIA in these cases (non-exhaustive):

1. **Systematic and extensive evaluation** of personal aspects based on
   automated processing, including profiling, on which decisions are based
   that produce legal or similarly significant effects (this is the core AI/
   ML trigger).
2. **Large-scale processing** of sensitive data (Article 9) — health,
   biometric, genetic, racial/ethnic, political, religious, trade union,
   sex life, criminal convictions.
3. **Systematic monitoring** of a publicly accessible area on a large scale.

The Article 29 Working Party (now EDPB) added more triggers via WP248:
- Evaluation or scoring (including profiling and predicting).
- Automated decision-making with legal/significant effect.
- Systematic monitoring.
- Sensitive data or data of highly personal nature.
- Data processed on a large scale.
- Matching or combining datasets (e.g., from different processing
  operations, or from two different controllers).
- Data concerning vulnerable subjects (children, employees, mentally ill,
  asylum seekers, elderly).
- Innovative use of technology or organisational solutions (this catches
  most new AI deployments).
- When the processing itself prevents data subjects from exercising a right
  or using a service/contract.

In practice: if you're deploying AI on personal data, assume a DPIA is
required. The bar is whether a DPIA might NOT be required — that's the
exception, not the rule.

## Symptom

An ML team launches a customer-churn-prediction model that scores all
users on likelihood to cancel. Scores feed into retention offers and, for
high-churn-risk users, into pricing changes. No DPIA was performed. The
team rationalises: "we're not making the decision, the model just suggests."
This is exactly the scenario Article 35(3)(a) describes — systematic and
extensive evaluation producing significant effects. The absence of a DPIA
is itself a GDPR violation, separate from any underlying harm.

## DPIA Contents — What Must Be Documented

GDPR Article 35(7) mandates a specific structure. Your DPIA must include:

1. **Systematic description of the processing operations and purposes.**
   Include the AI model architecture, training data sources, inference
   pipeline, who has access to outputs, retention periods, and the
   legitimate interest or consent basis (Article 6) plus any Article 9
   condition if sensitive data is involved.
2. **Assessment of necessity and proportionality.** Why AI? Why this data?
   Why this much data? Could a less-intrusive approach achieve the same
   business goal? Document the alternatives considered.
3. **Assessment of risks to the rights and freedoms of data subjects.**
   Enumerate concrete risks: discrimination, re-identification, inaccurate
   predictions causing financial/legal harm, loss of autonomy, exclusion
   from services. Score each by likelihood and severity.
4. **Measures to address the risks.** Safeguards, security measures,
   mechanisms to ensure protection of personal data and demonstrate
   compliance. Include technical measures (encryption, pseudonymisation,
   differential privacy, model cards) and organisational measures (human
   oversight, audit trails, training, escalation paths).

For AI-specific DPIAs, EDPB and national DPA guidance expect additional
content:

- **Data governance for training.** Provenance, consent status, bias
  audit results, representativeness analysis.
- **Model performance and limitations.** Accuracy across protected groups,
  known failure modes, monitoring plan for drift.
- **Explainability approach.** How will individual decisions be explained
  to data subjects under Article 22(3)?
- **Human oversight design.** Who reviews, with what authority, on what
  cadence, with what override capability.
- **Feedback and contestability mechanism.** How can a data subject
  challenge a decision?

## Gotchas

- **A DPIA is a process, not a document.** It must be a living artefact,
  reviewed when processing changes. A "completed" DPIA that nobody revisits
  after the model is retrained is non-compliant. Document the review cadence
  in the DPIA itself.
- **Retraining triggers DPIA review.** If you retrain on new data and the
  model's behaviour or risk profile changes, the DPIA must be revisited.
  Silent retraining without DPIA review is a common gap.
- **You cannot DPIA your way out of a violation.** A DPIA does not authorise
  unlawful processing. If the DPIA reveals high residual risk, you MUST
  either reduce the risk or consult the supervisory authority under Article
  36 (prior consultation). Proceeding anyway is worse than not doing the
  DPIA — you've documented that you knew.
- **Article 36 prior consultation is mandatory** if residual risk remains
  high after mitigation. Many teams skip this step. The penalty for skipping
  consultation is separate from the underlying processing violation.
- **The DPO must be involved.** Article 35(2) requires seeking the advice
  of the Data Protection Officer (where one exists). A DPIA authored without
  DPO input is procedurally deficient.
- **DPIA ≠ AI Act risk management system.** They are related but distinct.
  The AI Act requires a separate risk management system (Article 9) for
  high-risk systems. You may combine documents, but the combined artefact
  must explicitly satisfy both regimes' required contents. A single
  document titled "DPIA" that omits AI Act risk-management content does not
  satisfy the AI Act.
- **Vendor DPIAs are not transferable.** If you deploy a vendor's AI system,
  the vendor's DPIA covers THEIR processing as a processor. You, as
  controller, must conduct YOUR OWN DPIA covering your use-case, your
  purposes, your data subjects. Relying solely on a vendor DPIA is a common
  and fatal compliance error.
- **Children's data always triggers DPIA scrutiny.** Any AI processing data
  relating to children is presumptively high-risk. Do not attempt to argue
  otherwise.
- **DPIA must be published, in some cases.** Article 35(11)(a) requires
  publishing DPIAs for monitoring of publicly accessible areas on a large
  scale. Other DPIAs may be requested by the supervisory authority.
- **Track DPIA inventory.** Maintain a register of all DPIAs, their status,
  their last review date, and their next scheduled review. This is standard
  audit evidence and the first thing a regulator asks for.
- **Lack of a DPIA can be fined independently.** CNIL fined Google €50M
  (2019) partly for failure to conduct a proper DPIA for ad personalisation.
  The absence of a DPIA is itself the violation, not just an aggravating
  factor.

## DPIA Workflow for AI Projects

1. **Trigger check** — does this AI project meet any Article 35(3) criterion
   or WP248 criterion? If yes, mandatory. If unsure, consult DPO — default
   to conducting one for AI projects.
2. **Scoping** — define the processing precisely: data, purposes, subjects,
   model, deployment context.
3. **Risk identification** — enumerate threats to data subjects' rights.
4. **Risk assessment** — score each risk by likelihood and severity.
5. **Mitigation design** — specify safeguards; assign owners.
6. **Residual risk evaluation** — if high, escalate to Article 36 prior
   consultation.
7. **DPO review and sign-off.**
8. **Record in DPIA register** with review cadence.
9. **Operationalise mitigations** — this is where most DPIAs fail. The
   document exists but the safeguards are never implemented in the code.
10. **Schedule review** — at minimum annually, or on material change
    (retraining, new data source, new use-case, new jurisdiction).
