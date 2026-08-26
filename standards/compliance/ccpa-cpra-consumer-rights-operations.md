# ccpa-cpra-consumer-rights-operations

**Issue:** A business subject to the CCPA (as amended by the CPRA) must operate a working pipeline for the full bundle of consumer rights — know/access, delete, correct, opt-out of sale or sharing, and limit use of sensitive personal information — with statutory clocks attached: confirm receipt within 10 business days, substantively respond within 45 days, extendable once by 45 more with notice. Most CCPA material covers the opt-out signal handling (covered separately in this knowledge base) or the privacy-policy text; this runbook covers the operational core that actually fails audits and enforcement: request intake channels, proportionate identity verification, cross-system deletion orchestration with its exception list, authorized agents, appeals, and the recordkeeping duties — plus the CPPA's 2025 finalized regulations on ADMT, risk assessments, and cybersecurity audits that phase in from 2027.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The rights you must actually service

1. **Right to know/access.** Disclosure of the categories and specific pieces of personal information collected in the trailing 12 months, plus categories of sources, purposes, and third-party recipients. Deliver specific pieces via secure, authenticated export (the data-portability format is covered in `gdpr-data-portability-export.md`).
2. **Right to delete.** Obligation extends beyond your primary database: you must direct service providers, contractors, and third parties to whom you sold/shared the data in the trailing 90 days to delete as well — and you may deny deletion only under the statutory exception list (security incident forensics, legal obligations, debugging, exercise of free speech, etc.), telling the consumer which exception applied.
3. **Right to correct.** Correct inaccurate personal information, taking reasonable steps (given the nature and purpose of the data) to verify accuracy — CPRA's addition that most pipelines still lack a write-path for.
4. **Right to limit sensitive personal information.** Consumers may restrict use/disclosure of SPI (government IDs, financial account credentials, precise geolocation, race/ethnicity, religion, union membership, health/sex-life data, genetic and biometric identifiers, contents of mail/email combined with identifying data) to purposes tied to providing the goods/services — this is a use-limitation, not a deletion.
5. **Right to opt out of sale/sharing and non-discrimination.** No selling or cross-context behavioral advertising after opt-out, no retaliation (price, service, quality) for exercising any right; the GPC-signal mechanics live in `ccpa-opt-out.md`.

## The statutory clock and intake requirements

1. **10 business days to confirm.** Confirm receipt of the request and describe the verification process; the confirmation is a distinct, separately-timed duty that teams forget under the 45-day pressure.
2. **45 days to substantively respond, +45 with notice.** The substantive deadline runs from receipt; one extension is allowed with notice explaining the reason. If you cannot verify identity inside the window, you may deny with an explanation — the clock does not pause for slow consumers.
3. **Two or more designated submission methods.** At minimum two designated intake channels (webform plus email, or a toll-free number); requests received through any channel the business actually monitors count, including social media if you operate the account for consumer questions.
4. **Verification proportionate to sensitivity.** For password-protected-account requests made through that account, verify through the account itself. For other channels, match at least two data points already on file; step up verification for deletion of SPI. Over-verification (demanding ID scans for public-data access requests) is itself a violation pattern.
5. **Authorized agents.** Accept requests from a person or business registered with the Secretary of State acting as the consumer's agent (or with written/signature permission); require the agent to prove the consumer's identity and authorization.
6. **Appeals and recordkeeping.** Offer an appeal path for denials (respond within a reasonable period), and retain request records for 24 months showing what was asked, verification performed, response given, and basis for any denial.

## Deletion orchestration and edge cases

1. **Map deletion targets before the first request arrives.** Production databases, analytics/warehouses, logs, backups, CRM, support tools, email/marketing platforms, third-party processors — build a registry with each system's deletion mechanism (API, ticket to vendor, impossible-in-backup note) and SLA.
2. **Backups get a documented alternative.** If data cannot be deleted from backups, the accepted pattern is to exclude the deleted identity from restore paths and document the practice; restore tests must honor the exclusion list.
3. **Propagate the 90-day third-party directive.** For parties you sold to or shared with in the last 90 days, send deletion instructions via your existing vendor workflow and capture their confirmation as evidence.
4. **Correct is not delete-lite.** Correction needs an actual update write-path plus downstream sync; if verification or accuracy determination fails, explain why and let the consumer contest.
5. **Denials must cite the exception.** A bare "we cannot comply" fails; name the exception, tell the consumer, and log it for the 24-month record.

## 2025-2026 outlook: the CPPA rulemaking package

1. **ADMT regulations finalized 2025, compliance January 1, 2027.** Businesses using automated decisionmaking technology for significant decisions (hiring, lending, housing, education, healthcare services) must provide pre-use notices and opt-out/access mechanisms — inventory your ADMT use cases now.
2. **Risk assessments.** The finalized package adds mandatory risk assessments for higher-risk processing (including ADMT and sale/sharing of large volumes of PI), with submissions to the CPPA on a phased schedule beginning in 2027 — these overlap heavily with GDPR DPIA practice.
3. **Cybersecurity audits.** Phased in later (initial obligations for the largest businesses around 2028-2030 by revenue tier); governance documentation built now doubles as audit evidence.
4. **Enforcement posture.** The CPRA removed the CCPA's 30-day cure period — the CPPA and AG can pursue violations immediately, with administrative fines of $2,500 per violation and $10,000 per intentional violation or violations involving minors, each non-compliant request counting separately.

## Related

1. **`ccpa-opt-out.md`.** Opt-out/GPC signal handling mechanics.
2. **`ccpa-privacy-policy-requirements.md`.** The disclosure-layer obligations that complement this pipeline.
3. **`us-state-privacy-laws-2026-multi-state-compliance.md`.** How to generalize this pipeline to the state-law family (Virginia, Colorado, etc.) that mirrors CCPA mechanics with different clocks.
