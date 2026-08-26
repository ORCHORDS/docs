# psd3-psr-2026-legislative-state

**Issue:** The EU payment-services rulebook is being rewritten. The PSD3/PSR package — which splits PSD2 into a revised Payment Services Directive and a directly applicable Payment Services Regulation — passed its decisive negotiation milestone in late 2025 and is moving through formal adoption in mid-2026, with practical enforcement not expected before 2027. Payment teams treating PSD2 as settled law risk building flows (SCA exemption handling, refund UX, fraud data sharing, open banking access) that will need rework. This note captures where the legislation actually stands as of August 2026 and what changes matter for engineering.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Timeline: where the texts actually are

1. **27 November 2025 — provisional political agreement.** The European Parliament and Council concluded trilogue negotiations on PSR and PSD3, locking the political substance (Norton Rose Fulbright; Parliament legislative train).
2. **22 April 2026 — COREPER endorsement.** Member states' ambassadors endorsed the final trilogue texts, moving the package to formal adoption machinery (Freshfields).
3. **5 May 2026 — ECON committee approval.** The Parliament's economics committee signed off; plenary vote was anticipated June/July 2026 with formal adoption shortly after.
4. **Entry into force and transition.** PSR applies EU-wide 20 days after Official Journal publication plus an 18-month transition; PSD3, as a directive, requires national transposition with a longer (roughly two-year) window (Worldline). Realistic enforcement horizon: 2027.
5. **Adjacent but separate: FIDA.** The Financial Data Access regulation (open finance beyond payments) was still in trilogue as of April 2026 — do not conflate its timeline with PSD3/PSR.

## The PSD3/PSR split and why it matters

1. **PSR is a regulation, not a directive.** It applies directly and uniformly in all member states — no 25 divergent national transpositions. Provisions landing in PSR (much of the conduct-of-business and operational rulebook) will be enforced identically everywhere.
2. **PSD3 keeps the licensing architecture.** Authorization/passporting of payment institutions stays directive-level, preserving member-state supervision, but with tightened requirements (capital, governance, and enforcement powers).
3. **Practical effect for platforms.** Uniform conduct rules mean one compliance implementation instead of per-country interpretations — cheaper for pan-EU platforms, but also less room for national regulator forbearance.

## Key substantive changes vs PSD2

1. **Verification of payee (IBAN-name check) extended.** The payer's PSP must verify the payee name against the IBAN for all credit transfers, not just instant ones — this changes payout and disbursement UX (marketplaces, refunds, remittances) because name-mismatch warnings become mandatory everywhere.
2. **Fraud data sharing between PSPs.** PSD3 obliges PSPs to exchange fraud-related information across the chain (payer PSP <-> payee PSP), strengthening detection of authorized-push-payment scams; expect new data-exchange interfaces and liability weight on suspicious-beneficiary signals.
3. **SCA review.** The strong-customer-authentication requirements and their exemption framework (TRA thresholds, low-value caps) are being revised — the exact thresholds and exemption set that exist under the PSD2 RTS should be treated as transitional (see psd2-sca-exemption-strategies).
4. **Open banking / open finance groundwork.** PSD3/PSR rebalance access-to-account rules (XS2A), address API-standardization complaints from PSD2, and align with FIDA's broader data-access regime; dedicated interfaces and contingency measures get sharper teeth.
5. **Consumer protection and refunds.** Stronger rules on transparent fee disclosure and the refund process for unauthorized transactions, plus EU-level attention to APP-fraud reimbursement models — relevant to any wallet or pay-by-bank feature.

## What payment engineering teams should do now

1. **Inventory PSD2 dependencies.** List every place the codebase assumes PSD2-RTS behavior: SCA exemption flags, 3DS routing, mandate capture text, IBAN checks on payouts. Tag each as PSR-stable or PSR-revision-likely.
2. **Make SCA parameters configurable.** Thresholds (EUR 30 low-value cap, TRA bands) and exemption toggles must be PSP-config values, not constants, so the RTS revision lands as a config change.
3. **Plan the payee-verification UX.** Design now for name/IBAN mismatch warnings on every credit transfer — payout flows that batch silently will need a mismatch-resolution path (block, warn, or queue-for-review).
4. **Track issuer-side changes.** As issuers implement PSR obligations (stronger payee warnings, revised SCA), acceptance behavior shifts before enforcement dates; monitor PSP changelogs through 2026-2027 rather than assuming current auth behavior is permanent.
5. **Budget the 18-month clock.** From PSR entry into force, you have 18 months to full application — long enough to defer panic, short enough that a 2027 project scoped today should be written against PSR rules, not PSD2.

## Sources consulted (2025-2026)

1. **Norton Rose Fulbright** — "PSD3 and PSR: From provisional agreement to 2026 readiness" (trilogue conclusion, transition mechanics).
2. **Freshfields** — "PSD3/PSR: What the EU's new payments rules mean for your business" (COREPER endorsement April 2026).
3. **Worldline** — "The scope and timeline are locked in for PSD3 and PSR" (18-month PSR transition, transposition windows).
4. **European Parliament legislative train** — Revision of EU rules on payment services (procedural status).
5. **J.P. Morgan Payments insights** — PSD3 enforcement expectations (not before 2027).
