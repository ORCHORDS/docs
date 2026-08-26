# Automated Decision-Making and Profiling — Transparency Obligations (GDPR Art. 22 + EU AI Act)

> When: GDPR Article 22 grants data subjects rights regarding solely
> automated decisions with legal or similarly significant effects. The EU
> AI Act (2024-2026 enforcement) adds layered transparency obligations for
> AI systems that make or support such decisions. State laws (California,
> Colorado, others) add US-side profiling opt-out rights.
> Who: Any developer whose system makes, or materially informs, decisions
> about individuals based on automated processing of their personal data —
> hiring, credit, insurance, pricing, eligibility, fraud scoring, content
> moderation with account consequences.

## What Counts as "Automated Decision-Making"

GDPR Recital 71 and Article 22(1) cover decisions based **solely** on
automated processing — with no meaningful human involvement — that produce
**legal effects** (affects someone's legal rights: contract, employment,
benefits) or **similarly significantly affects** them (denial of credit,
employment rejection, insurance denial, ejection from a platform they rely
on for livelihood).

Note the narrowing: "solely" automated. But "solely" is interpreted
strictly. A human who rubber-stamps the model's output is NOT meaningful
human involvement. The human must have the authority and competence to
overturn the decision, and must genuinely exercise judgement.

For the EU AI Act, these systems often fall into Annex III high-risk
categories (employment, credit, essential services), triggering the full
high-risk obligation stack on top of GDPR Article 22 rights.

## Data Subject Rights Under Article 22

1. **Right not to be subject** to solely automated decisions with
   legal/significant effect — unless one of three exceptions applies:
   (a) necessary for a contract;
   (b) authorised by EU/Member State law;
   (c) based on the data subject's explicit consent.
2. **Right to obtain human intervention** — a real human with authority to
   overturn.
3. **Right to express their point of view** — a contestability mechanism.
4. **Right to contest the decision** — formal challenge pathway.
5. **Right to information** about the logic involved (Articles 13-15) —
   meaningful information about the processing, not source code.

## Symptom

A lending startup deploys a fully automated credit-decisioning model. An
applicant is denied with a templated email: "Based on our automated review,
we regret to inform you..." The system has no human-in-the-loop pathway,
no contestability mechanism, and the denial email provides no meaningful
explanation of the factors that led to the decision. The applicant is
based in the EU. This is a textbook Article 22 violation: solely automated,
legal/significant effect (credit denial), and no Article 22(2) exception
satisfied (no contract necessity — the decision IS the contract decision,
not a step toward it; no explicit consent collected; no Member State law
authorisation).

## Developer Obligations

### Transparency (Articles 13-15)
- Disclose the existence of automated decision-making in the privacy notice
  AT THE TIME of data collection, not just in a denial letter.
- Provide **meaningful information about the logic involved**. This does NOT
  require source code or model weights, but it DOES require:
  - The main categories of data used (e.g., "transaction history, payment
    timeliness, account age").
  - The relative importance of those factors (e.g., "payment history is the
    most important factor").
  - The general logic (e.g., "the model assigns a risk score based on these
    factors; higher scores correlate with higher default probability").
  - For high-stakes decisions, the right to explanation (Recital 71).

### Human Intervention and Contestability (Article 22(3))
- Provide a pathway for the data subject to request human review BEFORE a
  decision becomes final.
- Provide a pathway to contest AFTER a decision is made.
- Ensure the human reviewer has:
  - Authority to overturn.
  - Competence and training to understand the system.
  - Access to the relevant data and the model's output.
  - Time to genuinely review (not a 30-second rubber stamp).
- Document the human review process and retain records.

### Bias and Safeguards (Recital 71)
- Use appropriate mathematical/statistical procedures to prevent errors and
  discriminatory effects.
- Secure personal data in a manner proportionate to the risks.
- Document these safeguards in the DPIA.

### EU AI Act Convergence
For systems that are also high-risk under the AI Act:
- Human oversight design (Article 14) — must be built into the system, not
  just described in a manual.
- Transparency to deployers (Article 13) — instructions for use must
  disclose limitations and the supervising human's role.
- Automatic logging (Article 12) — events enabling post-hoc review.
- Fundamental rights impact assessment for certain deployers (Article 27).

### US State Law Layer
- California CCPA/CPRA: right to opt out of automated decision-making
  technology and profiling.
- Colorado, Connecticut, Virginia: opt-out of profiling that produces
  legal/significant effects.
- Universal opt-out signals (GPC) must be honoured for profiling opt-out.

## Gotchas

- **"Human-in-the-loop" that doesn't loop is not compliance.** A human who
  reviews 100% of model outputs and overturns 0% is not meaningful human
  involvement. Track overturn rates; if they're zero, the loop is a fiction.
- **The contract-necessity exception is narrow.** A credit-scoring system
  does NOT qualify under Article 22(2)(a) — the decision IS the contract
  decision, not a step necessary to enter into it. Most courts and DPAs read
  this exception narrowly.
- **Explicit consent can be withdrawn.** If you rely on Article 22(2)(c),
  the data subject can withdraw consent at any time. You must then provide
  the human-intervention pathway anyway or stop the processing.
- **"Logic involved" does not mean "we can't explain it."** If your model is
  a black box and you cannot provide meaningful information about the logic,
  you have two problems: (1) you cannot satisfy the transparency obligation,
  and (2) the model is not appropriate for solely automated decision-making.
  Use explainable approaches (interpretable models, post-hoc explanations
  like SHAP/LIME with documented limitations) for high-stakes decisions.
- **Profiling and ADM are different.** Profiling is any automated processing
  to evaluate personal aspects. ADM is a decision based on that profiling.
  You can profile without ADM (subject to other obligations), but ADM with
  legal/significant effect triggers Article 22 regardless.
- **US profiling opt-outs are not just email forms.** Multiple states
  require recognising universal opt-out signals (GPC). Build signal
  recognition, not just a "contact us" form.
- **Children's data heightens obligations.** Profiling of children is
  presumptively prohibited or restricted under multiple regimes (UK GDPR/AADC,
  California AADC, Maryland MODPA, COPPA 2.0 direction). Do not deploy
  profiling against minors without documented compelling justification.
- **Decision logs must be retained.** If a data subject contests a decision
  six months later, you must be able to reconstruct what happened. Logging
  is not optional. Retain per your state-law breach/notification clock AND
  GDPR accountability principles.
- **Explanations must be tailored to the recipient.** A denial explanation
  full of ML jargon does not satisfy the obligation. The data subject must
  be able to understand it.
- **AI Act "deployer" duties compound.** If you deploy a high-risk AI system
  for decision-making, you (as deployer) must use it only for its intended
  purpose, provide human oversight, monitor operation, and retain logs for
  at least 6 months. These stack on top of your GDPR Article 22 obligations.
- **Fraud-detection systems can trigger Article 22.** A fraud-scoring
  system that automatically blocks a user's account has legal/significant
  effect (denial of service). Ensure human-review pathway exists.
- **Pre-employment screening tools are high-risk.** Résumé screeners,
  interview-analysis tools, and background-check automation trigger BOTH
  Article 22 and AI Act Annex III (employment). Full obligation stack applies.

## Implementation Checklist

- [ ] Inventory every automated decision-making and profiling system.
- [ ] For each, classify: legal/significant effect? Solely automated?
- [ ] For solely-automated + legal/significant: identify which Art. 22(2)
  exception applies, or redesign to include meaningful human review.
- [ ] Implement contestability mechanism with documented human-review
  authority.
- [ ] Implement transparency: privacy notice disclosure + decision-specific
  explanation at point of decision.
- [ ] Build explainability approach (interpretable model or post-hoc
  explanation) and document limitations.
- [ ] Implement logging that enables post-hoc reconstruction.
- [ ] Implement US-state opt-out (including GPC recognition) for profiling.
- [ ] Conduct DPIA covering ADM risks.
- [ ] If AI Act high-risk: complete the full Annex III obligation stack.
- [ ] Train human reviewers on authority, competence, and the importance of
  genuine review (not rubber-stamping).
- [ ] Track and audit overturn rates; investigate near-zero rates.
- [ ] Retain decision logs per the longest applicable retention clock.
