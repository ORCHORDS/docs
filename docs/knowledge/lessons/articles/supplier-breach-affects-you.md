# supplier-breach-affects-you

**Issue:** Third-party vendor breaches expose your customer data and trigger your breach notification obligations even though you were not attacked
**Date:** 2026-08-11
**Status:** documented

## What happened
A CRM vendor was breached. The vendor had access to 18 months of customer contact data synced via API. The company had no record of what data had been shared, no contractual right to notification within 72 hours, and no inventory of which customers were affected. The GDPR notification deadline was missed, resulting in a regulatory investigation.

## The lesson
Every third-party vendor that receives personal data from you becomes part of your threat surface. You are responsible for their data handling under GDPR and similar regulations. Maintain a data processor inventory, require contractual notification SLAs, and know exactly what data each vendor holds.

## Why it matters
Vendor breaches are your breaches from a regulatory standpoint. You must notify affected individuals and authorities within the required window — which requires knowing what data was exposed. Without a vendor inventory and data-sharing map, you cannot comply.

## How to apply
- [ ] Maintain a vendor data inventory: who receives what categories of personal data, how it flows, and what data remains in their systems.
- [ ] Require DPA (Data Processing Agreement) or equivalent with every vendor that handles personal data.
- [ ] Require vendors to notify you of any breach within 24-48 hours contractually.
- [ ] Conduct annual vendor security assessments (questionnaire minimum, audit for high-risk vendors).
- [ ] Minimize data shared with vendors — only send what they actually need.

## Related
- `open-source-dependency-audit.md`
- `gdpr-by-design-not-retrofit.md`
- `data-minimization-reduces-breach-impact.md`
