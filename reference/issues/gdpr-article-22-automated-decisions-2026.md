# gdpr-article-22-automated-decisions-2026

**Issue:** A user is denied a loan by an AI system. The denial text says "your application has been declined" with no explanation. The user requests a human review under GDPR Article 22. The team has 30 days to provide meaningful information about the logic involved.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

GDPR Article 22 gives individuals the right not to be subject to a decision based solely on automated processing, including profiling, that produces legal or similarly significant effects. The Court of Justice of the EU's 2023 SCHUFA ruling (C-634/21) and 2025 Dun & Bradstreet ruling (C-203/22) expanded the practical scope well beyond what most enterprises had assumed. A wide set of AI use cases now requires Article 22 analysis as a default, not as an edge case.

## Root cause

Article 22 applies when a decision is made solely by automated means and produces legal or similarly significant effects. Three exceptions allow such decisions:

- Necessary for entering into or performing a contract
- Authorized by EU or Member State law
- The individual has given explicit consent

Even where one of the three exceptions applies, Article 22(3) requires safeguards: at minimum, the right to obtain human intervention, to express a point of view, and to contest the decision.

Articles 13(2)(f), 14(2)(g), and 15(1)(h) layer on transparency obligations: when Article 22 applies, the controller must give the data subject "meaningful information about the logic involved, as well as the significance and the envisaged consequences."

## The SCHUFA and Dun & Bradstreet rulings

**SCHUFA (December 2023, C-634/21):** A credit reference agency creating credit repayment probability scores through automated processing constitutes automated individual decision-making under Article 22 — even when the score is passed to a separate lender who makes the final decision. The Article 22 obligations fall on the entity running the algorithm, not just the entity acting on its output.

**Dun & Bradstreet (February 2025, C-203/22):** Organizations must provide data subjects with sufficient information about "the procedure and principles actually applied" in automated decision-making. Crucially, organizations **cannot simply invoke trade secrets** to deny individuals access to this information. The right of access cannot be excluded as a rule.

## The 2026 expanded scope

The EDPB 2024 guidelines, building on SCHUFA, expanded practical scope:

- "Solely automated" includes cases where a human is nominally in the loop but does not exercise meaningful authority — a rubber-stamp human is not human oversight
- "Similarly significant effects" includes pricing, eligibility, employment screening, fraud flags, content moderation that affects livelihood, and access to public services
- The transparency obligation requires meaningful explanation of the logic, not a generic statement that "AI is used"

AI use cases now in scope as a default:

- Credit scoring
- Debt-collection prioritisation and contact-strategy systems
- Insurance underwriting and claims-fraud scoring
- Hiring and CV-screening systems
- Tenant-screening systems
- Employee-performance and dismissal-risk scoring
- Content-moderation and account-suspension decisions on platforms where this affects livelihood

Conversely, decisions that are genuinely advisory — where a competent human reviews the AI output, has authority to override, has time and information to do so, and exercises that authority in practice — fall outside Article 22(1).

## The four individual rights

1. **Right to obtain human intervention.** A human with appropriate authority reviews the automated decision. That person must have access to the information the algorithm used and the ability to change the outcome — not just document the request.
2. **Right to express your point of view.** Before a final decision, or as part of a review, present facts, context, or additional evidence the algorithm could not assess.
3. **Right to an explanation.** Under GDPR Articles 13, 14, and 22 read together, entitled to meaningful information about the logic involved, the significance of the processing, and the envisaged consequences. The explanation must be specific enough to allow the data subject to understand and challenge the outcome.
4. **Right to contest the decision.** If you disagree with the automated outcome — or with the explanation — formally contest it. Contestation triggers a duty on the controller to re-examine under human oversight.

## The compliance pattern

A six-element compliance pattern:

1. **Per-system Article 22 analysis** — in or out of Article 22(1), and if in, which Article 22(2) lawful basis applies.
2. **Meaningful human-review design** — the reviewer has the AI output, the underlying data, the rationale, and authority and time to override.
3. **Explanation interface** — gives data subjects a clear, non-trivial description of the logic, the significance, and the envisaged consequences.
4. **Access-rights workflow** — can produce the per-decision explanation when an Article 15(1)(h) request comes in.
5. **Contest-and-appeal workflow** — with an SLA.
6. **Monitoring layer** — detects when the human-review rate drops below the threshold that makes the human meaningful.

## The AI Act Article 86 overlap

Article 86 of the EU AI Act creates a right to explanation that goes beyond GDPR Article 22. While Article 22 only covers decisions made "solely" by automated means, AI Act Article 86 covers any decision where a high-risk AI system's output produces legal effects — **even when a human is in the loop**.

This closes the "human-in-the-loop loophole" that many organizations have relied on to avoid Article 22 obligations. A rubber-stamp human is not human oversight for either regulation.

## The meaningful logic disclosure

Not a copy of the model weights, and not a generic statement that "machine learning is used." The EDPB has indicated that meaningful logic disclosure includes:

- The input variables and their relative importance to the outcome
- The decision rule or threshold structure
- The training-data domain and known limitations
- A worked example or counterfactual where relevant

The disclosure must be in clear and plain language. A PhD-level explanation is not meaningful to a non-technical data subject.

## The fine framework

Article 83 of the GDPR sets the fine framework:

- Up to **EUR 20 million or 4% of global annual turnover**, whichever is higher, for breaches of the lawful-basis and data-subject-rights provisions including Article 22
- For an enterprise at EUR 1B turnover, that's EUR 40M for an Article 22 violation

## The required artifacts

At minimum:

- The per-system Article 22 analysis (in/out of scope, lawful basis, safeguards)
- The data protection impact assessment under Article 35
- The explanation framework and the explanation surfaced to data subjects
- The human-review process and monitoring evidence
- The contest-and-appeal procedure and case log
- Records of access requests under Article 15(1)(h) and the responses
- The privacy notice text under Articles 13/14

## The UK divergence

Section 80 of the Data (Use and Access) Act 2025 came into force on 5 February 2026, replacing Article 22 of the UK GDPR with a fundamentally different model. Organisations can now carry out automated decision-making using any lawful basis, including legitimate interests, provided mandatory safeguards are in place. The safeguards are set out in the new Article 22C:

- Provide the data subject with information about the decision
- Enable the data subject to make representations
- Enable the data subject to obtain genuine human intervention
- Enable the data subject to contest the decision

The stricter regime is preserved only where special category data is involved. A team operating in the UK must follow Article 22C, not the EU Article 22 directly, but the practical implications are similar.

## Verification

The tell that Article 22 compliance is working:

- Every AI system in scope has a documented Article 22 analysis (in/out, lawful basis, safeguards)
- A human-review process exists with documented authority, time, and information access
- A SAR workflow can produce a per-decision explanation within 30 days
- The contest-and-appeal procedure has an SLA, a case log, and demonstrated response
- The privacy notice under Articles 13/14 explicitly discloses automated decision-making use
- A monitoring layer tracks the human-review rate and alerts on drops below threshold

The tell it isn't:

- A user is denied with no explanation; legal gets the call
- The team cannot name which AI systems are in scope
- The "human review" is a rubber stamp — the human cannot override
- Trade secrets are invoked to deny explanation (this fails after Dun & Bradstreet)

## Gotchas

- **"Solely automated" includes rubber-stamp humans.** A nominal human in the loop without authority is not human oversight.
- **Trade secrets do not justify denying explanation.** Dun & Bradstreet (Feb 2025) closed this gap.
- **The transparency obligation is "meaningful information," not "model weights."** A generic "AI is used" statement is not compliant.
- **The right to explanation extends beyond GDPR via AI Act Article 86.** Even non-Annex-III high-risk systems face this.
- **The fine is the higher of EUR 20M or 4% of turnover.** For a global enterprise, that's the percentage number.
- **UK has diverged under the Data (Use and Access) Act 2025.** UK Article 22C is more permissive but still requires safeguards.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — the AI Act, including Article 86
- `lessons/ai-explainability-2026.md` — the technical mechanisms for explanation
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification triggers AI Act Article 86

## Source URLs (verified 2026-08-10)

- https://www.aiqarus.com/blog/gdpr-ai-data-protection
- https://expert-zoom.com/gb/magazine/legal/gdpr-ai-decision-making-rights-2026-how-to-challenge-automated-decisions-under-article-22
- https://academic.oup.com/idpl/article/16/2/ipag008/8696574
- https://www.hlc.com/en/publications/ai-and-automated-decisionmaking-in-the-uk-part-i-the-new-rules-and-regulatory-guidance
- https://impetora.com/answers/gdpr-article-22-automated-decisions
