# Tip and Prompt Screen Disclosure

## Scope

This article applies to retail and hospitality point-of-sale prompts and on-screen disclosures that present suggested tip amounts, default gratuities, service charges, or charitable round-up requests before the customer authorizes payment. It addresses design and evidence controls for screens, printed receipts, mobile payment flows, and self-service kiosks where a suggested tip or prompt can materially influence the amount actually charged. The focus is the consumer-credit disclosure framing used by the Consumer Financial Protection Bureau under Regulation Z (12 CFR Part 1026), particularly the Truth in Lending Act's general disclosure and conspicuousness principles for closed-end credit, rather than any specific state's wage-and-tip credit rules. The control also references the FTC's general prohibition on unfair, deceptive, or unsubstantiated representations under Section 5 of the FTC Act, which courts have long treated as a baseline for tip-prompt clarity claims.

The scope covers four surfaces: cashier-facing terminals with customer-facing prompts, handheld card readers and QR-code flows, pay-at-table tablets, and unattended kiosks or fuel-pump card readers. It does not replace state or municipal rules on tip pooling, service-charge characterization, or wage notice, and it does not address back-of-house tip distribution.

## Workflow or implementation guidance

Treat a tip or prompt screen as a transactional communication with the same scrutiny as an advertising or credit disclosure. Begin by classifying every prompt element: suggested percentage, flat dollar amount, default-selected option, "no tip" option, charitable round-up, and any accompanying descriptive language. For each element, identify the triggering surface, the default state, the modification path, and the final charge presented for authorization.

Suggested prompts should be expressed as plain-dollar or plain-percent representations of the subtotal subject to tip. Mixed unit representations (for example, "20% / $4.00") may confuse customers when the subtotal differs from the displayed basis; resolve this by anchoring to a single basis and showing the derived amount only as supplementary information. The "no tip" option must be visually and operationally equivalent to a paid option; it should not require extra taps, an unjustified default switch, or a screen change that the paid options do not require.

Pre-authorization screens must show the merchant's calculated total, including tax, prior tip handling, and any service charge, on the same surface as the tip prompt or on the next adjacent step. Screens that show only the prompt without the running total, or that defer the total to a confirmation surface several taps later, undermine the conspicuousness principle. Payment-tokenized flows (NFC, mobile wallet, saved-card) should mirror the same disclosure on the device that the customer is actually viewing when authorizing the charge.

For credit-card transactions, treat suggested prompts and the resulting charge as part of the same transaction. The credit-sale disclosure framing under 12 CFR Part 1026 does not require a TILA box on a tip prompt, but the practice of presenting a clear base amount, a separately itemized tip, and a final total before authorization reflects the same conspicuousness principle that Regulation Z uses for closed-end credit disclosures.

## Controls

Use a prompt-rendering review board with representatives from product, payments, legal, and accessibility. Maintain a prompt catalog indexed by surface, payment instrument, transaction type, and jurisdiction. Each catalog entry records the default state, the alternatives, the calculation formula, and the resulting authorization screen.

Technical controls should enforce that (1) the "no tip" option is rendered at the same size, contrast, and position as the suggested options unless the entire prompt block meets a documented accessibility exemption; (2) default selections can be changed with a single tap from the prompt screen; (3) the prompt never presents a previously selected tip after a customer has deselected it; (4) the authorization total always matches the sum of subtotal, tax, tip, and any service charge rounded consistently with stated policy; and (5) the merchant retains a server-side record of the prompt state at the moment of authorization.

Monitor key risk indicators: tip rate by surface, distribution of "no tip" selections, abandonment between prompt and authorization, customer complaints to card issuers or the CFPB, chargeback reason codes tied to "unrecognized amount," and any regulator inquiry. Investigate shifts that cannot be explained by customer mix or seasonality.

## Validation evidence

Capture a server-side render snapshot for each prompt variant including default state and final state. Retain for the longer of the issuer retention period, the antitrust or consumer-protection statute-of-limitations window, or the organization's records-retention schedule. Evidence should include the prompt text, the layout metadata (size, contrast, position), the resulting tip amount, the authorization amount, and the merchant's mapping from the prompt version to the charge.

Sample testing should compare the rendered screen to the catalog entry, recalculate the tip independently, verify the no-tip path, and confirm the authorization total. Periodic third-party reviews of pay-at-table tablets, unattended kiosks, and mobile flows provide additional assurance.

## Failure modes and correction

Common failures include hiding the no-tip option behind a smaller button, defaulting to a high percentage on a cramped screen, prompting for tip on transactions where tipping is not customary (for example, a self-service fuel pump) without offering an immediate skip, presenting a "tip" that is actually a service charge or convenience fee, and using dark patterns that re-select a previously removed tip on a subsequent screen.

When a defect is identified, pause the affected surface, deploy a corrected prompt version, retain the prior version's evidence, and conduct a bounded lookback of affected transactions. Remediate affected customers consistent with the nature of the defect: a corrected authorization if the prompt materially misrepresented the charge, a goodwill credit if the prompt was unclear but the charge was lawful, or a written explanation if the customer was correctly informed and the charge was authorized. Preserve the root-cause record, the population analysis, and the correction evidence.

Escalate matters that suggest systemic deception, repeated chargebacks tied to the same prompt, regulator inquiries, or class-action exposure to qualified counsel before issuing customer-facing explanations.

## Limitations

This article is operational guidance for prompt rendering and disclosure, not legal advice. It does not address every state's tip-credit, service-charge, or surcharging rule; wage and hour obligations to tipped employees; IRS tip-reporting requirements under § 6053 of the Internal Revenue Code; or payment-network rules on surcharging. The Reg Z framing here is structural and is not a substitute for a closed-end or open-end credit disclosure analysis. Where a tip prompt is part of a BNPL or other credit product, the applicable Regulation Z subpart and disclosure content will control.

## Canonical sources

- Consumer Financial Protection Bureau, **Rules and policy**: https://www.consumerfinance.gov/rules-policy/
- Electronic Code of Federal Regulations, **12 CFR Part 1026 (Regulation Z, Truth in Lending)**: https://www.ecfr.gov/current/title-12/chapter-X/part-1026
- Electronic Code of Federal Regulations, **12 CFR Part 1005 (Regulation E, Electronic Fund Transfers)** for adjacent consumer-payment disclosure framing: https://www.ecfr.gov/current/title-12/chapter-X/part-1005
- Federal Trade Commission, **FTC Act Section 5 overview** (general unfair-or-deceptive baseline for tip-prompt clarity): https://www.ftc.gov/advice-guidance/competition-guidance/guide-antitrust-laws/deceptive-practices
