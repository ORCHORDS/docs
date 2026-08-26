# soc2-type1-vs-type2-certification-path

**Issue:** A SaaS company hits enterprise deal friction and is told by procurement "we need your SOC 2 report." The team then has to decide between SOC 2 Type I and Type II, whether to do Type I at all, which trust services criteria to include, how long the observation window must be, and how to cover the gap between the end of the audit period and report issuance (the bridge-letter problem). Choosing wrong is expensive in both directions: skipping straight to Type II with immature controls burns a 6-12 month observation window on exceptions and qualified opinions, while stopping at Type I gets discounted by sophisticated buyers who read "point-in-time" as "untested in operation."

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Type I and Type II actually certify

1. **Type I — design suitability at a point in time.** The auditor tests whether your control environment was appropriately designed and implemented as of a specific date. No operating-effectiveness testing. It answers "did they build the right controls?" and is achievable in roughly 4-10 weeks of readiness work plus a short fieldwork window.
2. **Type II — operating effectiveness over a period.** The auditor samples evidence across an observation window (minimum credible window ~3 months, common windows 6-12 months) and tests that each control actually operated throughout. This is the report enterprise procurement treats as the real bar; nearly every serious buyer asks "is it Type II?"
3. **The Trust Services Criteria scope decision.** Security (Common Criteria, the TSC "Common Criteria" family CC1-CC9) is mandatory; Availability, Processing Integrity, Confidentiality, and Privacy are optional add-ons. Pick criteria by what customers and contracts require — most B2B SaaS does Security plus Availability and/or Confidentiality — because each added criterion multiplies evidence surface.
4. **Report anatomy buyers care about.** A Type II includes a management assertion, system description (Section 3), the auditor's opinion, control descriptions and test results, and Complementary User Entity Controls (CUECs). Qualified opinions and exceptions in Section 4 are not disqualifying but must be explainable with remediation status.

## The recommended path and timeline

1. **Readiness assessment first (2-6 weeks).** Map current practice against the chosen criteria — access management (CC6), change management (CC8), operations/monitoring (CC7), risk assessment and HR/onboarding (CC1-CC5). Output is a gap list with owners and dates.
2. **Remediate gaps and write policies (1-3 months, parallel-tracked).** Controls must exist and have been operating before the window starts; you cannot retroactively manufacture evidence. This is where policy documentation, ticket-based change management, and quarterly access reviews get institutionalized.
3. **Type I as an optional intermediate.** Do Type I when you need something in customers' hands quickly (deal deadlines, early enterprise motion) or want a low-stakes dress rehearsal of fieldwork. Skip it when controls are already mature and you can afford to wait for a Type II — buyers who accept Type I usually accept a bridge letter too.
4. **Start the Type II observation window immediately after (or instead).** The window is fixed on a calendar: controls are sampled across the whole period, so a control implemented mid-window is an exception for the months it did not exist. Common pattern: 6-month window for the first Type II (balancing speed and credibility), moving to a 12-month annual cycle thereafter.
5. **Fieldwork and issuance lag.** After the period ends, the auditor needs weeks (commonly 4-8) to complete testing and issue the report — during which the report does not yet exist.
6. **Bridge letters cover the gap.** For the period between observation-window end and report issuance (and until the next report lands), management issues a bridge/gap letter asserting no material changes; auditors often countersign. Make producing these a standing quarterly operation once you're on the annual cadence.

## Evidence collection that survives fieldwork

1. **Access reviews on a calendar.** Quarterly reviews of production access, admin roles, and service accounts with documented approvals — the single most-sampled control in SOC 2 fieldwork.
2. **Ticket-driven change management.** Every production change traceable to a ticket with peer review and approval; auditor samples tickets from the whole window, so the process must hold from day one.
3. **Onboarding/offboarding records.** Offer letters, background checks where applicable, access grants tied to start dates, terminations with access revocation timestamps inside your SLA.
4. **Security operations evidence.** Vulnerability scans on schedule, triaged findings, incident tickets, BCP/DR test results, vendor reviews — CC7 lives or dies on this operational exhaust.
5. **Automate continuously.** Pulling evidence on a continuous basis (drift detection, HRIS-to-IdP reconciliation, automated screenshots of configurations) turns fieldwork from an archaeology dig into an export; manual evidence assembly for a 12-month window is the main reason audits blow past budget.

## Gotchas

1. **Type I ≠ easier forever.** Buyers increasingly auto-reject point-in-time reports for sensitive data processing; treat Type I as scaffolding, not a destination.
2. **A qualified Type II is worse than a delayed clean one — usually.** Exceptions become permanent artifacts customers ask about; if a control will only be live part of the window, shift the window.
3. **CUECs cut both ways.** Your report's Complementary User Entity Controls shift responsibilities onto customers; sales teams that don't understand this overpromise what the report covers.
4. **Criteria scope is sticky.** Dropping a criterion later looks like regression to buyers; adding one restarts evidence collection for that family. Scope deliberately at the start.
5. **Auditor capacity is seasonal.** Fieldwork slots around January 1 and April 1 observation-window starts book out months ahead; engage the CPA firm before you fix the window date.

## Related

1. **`soc2-compliance.md` / `soc2-continuous-compliance.md`.** Baseline program and the continuous-monitoring model.
2. **`soc2-evidence-collection-automation.md`.** Tooling patterns referenced above.
3. **`soc2-type2-controls-mapping.md` / `soc2-cc6-logical-access-controls.md`.** Control-level mapping once the path is chosen.
