# FTC Negative Option Click-to-Cancel Controls

## Scope

This control applies to marketing, ecommerce, membership, lead-generation, subscription, continuity-plan, free-trial, automatic-renewal, and save-offer flows that use a negative option feature. A negative option feature is any arrangement where silence, failure to take an affirmative action, or failure to reject goods or services is treated as acceptance or continuing consent. The control covers the full customer journey: offer design, pre-billing disclosures, enrollment consent, account creation, billing, cancellation, retention offers, suppression, complaint handling, and evidence retention.

This document is not legal advice and does not assert that any specific FTC rule is currently enforceable against any specific organization. Teams must verify the applicable legal status with counsel before relying on a rule text, especially where litigation, effective dates, or agency revisions may affect obligations. The operational baseline here uses primary FTC materials as canonical references, including the FTC page for the [Negative Option Rule and click-to-cancel rulemaking](https://www.ftc.gov/legal-library/browse/rules/negative-option-rule) and the FTC business guidance on [negative options and recurring subscriptions](https://www.ftc.gov/business-guidance/blog/2024/10/click-cancel-ftcs-amended-negative-option-rule-what-businesses-need-know).

## Requirements Versus Recommendations

Requirements are obligations the organization has adopted as mandatory controls because they map to statutes, rules, consent orders, platform terms, or internal risk appetite. Recommendations are practices that reduce dispute, chargeback, complaint, and regulator risk but may not be independently required in every jurisdiction or channel.

Required controls:

- Present material offer terms before collecting billing information or obtaining enrollment consent.
- Obtain express informed consent for the negative option feature separately from general terms acceptance.
- Provide a cancellation mechanism that is at least as easy to use as the enrollment mechanism, using the same channel where practical.
- Do not require a customer to listen to or accept a save offer before cancellation is completed.
- Record cancellation requests promptly and stop future recurring charges after the effective cancellation date.
- Preserve evidence showing the disclosure, consent, confirmation, billing, and cancellation experience used for each customer.

Recommended controls:

- Use plain-language renewal notices even where not clearly required.
- Provide one-click account cancellation when the customer enrolled online.
- Send immediate cancellation confirmations by email or in-app message.
- Maintain a weekly governance review of complaint spikes, refund trends, and cancellation funnel abandonment.

## Workflow

The marketing owner starts each negative option campaign by completing a recurring-offer intake. The intake identifies product, price, trial duration, renewal cadence, cancellation path, refund policy, billing descriptor, sales channel, jurisdictions targeted, and any partner or affiliate involved. Legal reviews the proposed disclosures and consent layout before launch. Product or engineering confirms that enrollment and cancellation telemetry can be captured without storing sensitive payment data in marketing tools.

Before launch, QA tests the enrollment path from a clean browser session and a returning-user session. The test must capture screenshots or rendered page archives showing the offer page, checkout page, consent control, payment submission, confirmation page, and post-enrollment account view. QA also tests cancellation using each channel offered to customers, including web self-service, mobile app, phone, chat, email, or partner-managed cancellation where applicable.

After launch, operations monitors a daily control report. The report compares enrollments, cancellations, failed cancellations, refund requests, chargebacks, complaints, average cancellation time, cancellation funnel exits, and repeat billing after cancellation. Any anomaly moves to correction workflow. The owner must decide whether to pause acquisition, disable a variation, issue refunds, change copy, or escalate to counsel.

## Concrete Fields And Controls

Each campaign record must include these fields:

- `offer_id`: stable identifier for the specific offer and creative.
- `negative_option_type`: trial conversion, automatic renewal, continuity plan, prenotification plan, membership, or other.
- `seller_name`: legal entity shown to the customer.
- `billing_descriptor`: descriptor expected on customer statements.
- `initial_price`: amount charged at enrollment.
- `renewal_price`: amount charged after trial or promotional period.
- `billing_frequency`: weekly, monthly, annual, usage-based, or custom.
- `trial_or_promo_end_date_logic`: date calculation and timezone rule.
- `material_terms_url`: canonical terms presented before consent.
- `consent_text_version`: exact version of negative option consent copy.
- `consent_control_type`: checkbox, button, signature, recorded verbal consent, or other affirmative act.
- `consent_separate_from_terms`: yes or no.
- `cancellation_url_or_channel`: primary cancellation path.
- `save_offer_presented`: yes or no.
- `save_offer_optional`: yes or no.
- `cancellation_confirmation_template`: message version sent after cancellation.
- `retention_period`: evidence retention schedule.
- `owner`: accountable business owner.
- `legal_review_id`: approval ticket or review note.

Controls must prevent prechecked boxes for enrollment consent. The consent text must be visually proximate to the action that enrolls the customer and must state the recurring nature of the charge, charge amount or calculation method, charge frequency, when billing begins, and how to cancel. The cancellation control must be accessible from the account, subscription, billing, or settings area without requiring the customer to search help articles. Where phone cancellation remains available, call scripts must not obscure the customer’s ability to cancel.

## Validation Evidence And Tests

Evidence must be sufficient for an independent reviewer to reconstruct what the customer saw and did. Minimum evidence includes screenshots or HTML archives of disclosures, a consent event with timestamp and source, payment confirmation, renewal notice where used, cancellation event, cancellation confirmation, and billing suppression record.

QA tests must include:

- Enrollment disclosure test: verify material terms appear before payment submission.
- Consent separation test: verify recurring billing consent is separate from generic terms acceptance.
- No default consent test: verify consent is not preselected.
- Same-channel cancellation test: enroll online and cancel online without live-agent dependency.
- Save-offer bypass test: verify a customer can reject or skip retention offers and still cancel.
- Post-cancellation billing test: verify no recurring charge is created after cancellation effective date.
- Evidence replay test: retrieve the exact copy and UI version tied to a customer event.
- Accessibility test: verify the consent and cancellation controls can be reached and activated by keyboard and screen reader.

The internal evidence package should cite the FTC’s primary sources, including the [FTC Negative Option Rule page](https://www.ftc.gov/legal-library/browse/rules/negative-option-rule) and the [Federal Register publication for the negative option rulemaking](https://www.federalregister.gov/documents/2024/11/15/2024-25534/negative-option-rule).

## Failures And Corrections

Common failures include hiding renewal price below the fold, bundling recurring billing consent with unrelated terms, using a confusing “continue” button that enrolls the customer, forcing online customers to call to cancel, requiring account reauthentication after the customer has already authenticated, delaying cancellation until an agent responds, or continuing to bill after cancellation.

Corrections must be proportional to customer impact. If disclosures were incomplete, pause the affected offer, replace the creative, and identify enrolled customers who saw the defective version. If consent evidence is missing, stop billing until counsel approves a remediation approach. If customers were charged after cancellation, issue refunds and confirm suppression. If cancellation friction caused abandonment, simplify the flow, remove mandatory save offers, and retest the path before resuming acquisition.

Each incident record must identify root cause, affected offer IDs, affected customer population, refund decision, corrective owner, completion date, and evidence retained. Repeat failures within two quarters require executive review because recurring billing defects can indicate a governance failure rather than an isolated copy issue.

## Limitations

This control does not determine whether a particular subscription model is lawful in every state, country, or sector. It does not replace state automatic-renewal-law review, payment-network requirements, app-store rules, telecom rules, or sector-specific obligations. It also does not assume that an FTC rule, rule amendment, or implementation date is valid or enforceable without current legal verification. The control is intentionally conservative: it treats clear disclosures, affirmative consent, easy cancellation, and evidence retention as baseline governance even when a specific legal source may be contested or not yet applicable.

Marketing may not treat a passing checklist as permission to launch a deceptive offer. If the net impression of the promotion could mislead a reasonable customer about price, recurrence, cancellation, or refund rights, the campaign must be corrected before launch.

## Canonical sources

- **Primary authority 1 — Negative Option Rule and click-to-cancel rulemaking:** [https://www.ftc.gov/legal-library/browse/rules/negative-option-rule](https://www.ftc.gov/legal-library/browse/rules/negative-option-rule)
- **Primary authority 2 — negative options and recurring subscriptions:** [https://www.ftc.gov/business-guidance/blog/2024/10/click-cancel-ftcs-amended-negative-option-rule-what-businesses-need-know](https://www.ftc.gov/business-guidance/blog/2024/10/click-cancel-ftcs-amended-negative-option-rule-what-businesses-need-know)
- **Primary authority 3 — Federal Register publication for the negative option rulemaking:** [https://www.federalregister.gov/documents/2024/11/15/2024-25534/negative-option-rule](https://www.federalregister.gov/documents/2024/11/15/2024-25534/negative-option-rule)
