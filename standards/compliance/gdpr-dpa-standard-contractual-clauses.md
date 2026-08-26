# gdpr-dpa-standard-contractual-clauses

**Issue:** Executing valid Data Processing Agreements and Standard Contractual Clauses for international data transfers under GDPR Art. 28 and Art. 46
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Any SaaS product that processes personal data on behalf of customers is a "processor" under GDPR. Customers (controllers) are required to sign a DPA with every processor. Additionally, transferring personal data outside the EEA to countries without an adequacy decision requires a transfer mechanism — most commonly the EU Standard Contractual Clauses (SCCs) adopted in June 2021.

## Pattern / Solution
**DPA structure (minimum required content per Art. 28(3)):**

```
1. Subject matter and duration
2. Nature and purpose of processing
3. Type of personal data and categories of data subjects
4. Controller obligations and rights
5. Processor obligations:
   a. Process only on documented instructions
   b. Ensure confidentiality of personnel
   c. Implement appropriate technical/organisational measures (Art. 32)
   d. Respect sub-processor conditions (Art. 28(2))
   e. Assist with DSRs, breach notification, DPIAs
   f. Delete or return data on termination
   g. Provide audit assistance
```

**SCCs for international transfers (2021 Implementing Decision):**

Choose the correct module based on the transfer scenario:

| Module | Scenario |
|---|---|
| Module 1 | Controller → Controller (e.g., US analytics vendor receiving EU customer data) |
| Module 2 | Controller → Processor (most common for SaaS) |
| Module 3 | Processor → Processor (sub-processor in a third country) |
| Module 4 | Processor → Controller (data sent back) |

Steps to implement:
1. Identify all data flows leaving the EEA (using a data flow map).
2. For each third-country recipient, check the adequacy decision list (EU Commission website).
3. For non-adequate countries: execute the appropriate SCC module — no modifications to the core clauses are permitted.
4. Conduct a **Transfer Impact Assessment (TIA)** to verify the destination country's law does not undermine the SCCs.
5. Implement supplementary measures if the TIA identifies gaps (encryption, pseudonymisation, contractual commitments).

**Sub-processor management:**
```python
# Maintain a sub-processor register
sub_processors = [
    {"name": "AWS", "country": "US", "mechanism": "SCC Module 3", "purpose": "Cloud infrastructure"},
    {"name": "Stripe", "country": "US", "mechanism": "SCC Module 2", "purpose": "Payment processing"},
]
# Notify customers 30 days before adding a new sub-processor (recommended practice)
```

## Gotchas
- Using the old 2010 SCCs after December 2022 renders the transfer invalid — ensure you've migrated to the 2021 SCCs.
- The UK has its own transfer mechanism (IDTA / UK Addendum to EU SCCs) — EU SCCs alone do not cover UK→third-country transfers.
- An adequacy decision (e.g., EU–US Data Privacy Framework) can be invalidated by court ruling (as happened with Privacy Shield) — have SCCs ready as a fallback.
- DPAs must be updated when the processor's sub-processor list changes materially.
- Audit rights in the DPA must be real — a clause allowing "audits subject to mutual agreement" that the processor can veto is insufficient.
- DPAs are not optional even for "standard" SaaS tools — CNIL and other DPAs regularly fine controllers for missing DPAs with analytics vendors.

## Related
- `gdpr-adequacy-2026.md`
- `gdpr-data-subject-rights-api.md`
- `vendor-security-assessment.md`
- `privacy-by-design-checklist.md`
