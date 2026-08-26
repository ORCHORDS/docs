# security-policy-lifecycle-management

**Issue:** Organizations write a security policy set once (usually to land a SOC 2 or ISO 27001 audit) and then let it rot: policies lose owners after reorgs, go stale against practice, accumulate exceptions nobody re-reviews, and contradict each other across documents. Auditors consistently flag this pattern — an unreviewed policy past its own review date, or a policy that describes controls that don't match reality, is an easy nonconformity — and it gets worse as frameworks multiply, because teams maintain parallel near-duplicate policy sets for SOC 2, ISO 27001, and PCI DSS instead of one governed hierarchy mapped to many frameworks. What's missing is a managed lifecycle: authored, approved, published, attested, monitored, exception-tracked, reviewed, and retired like any other controlled artifact.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The document hierarchy to govern

1. **Policy.** Short, board-or-CISO-owned statements of intent: what must be true and why (for example, "access to production is granted on least-privilege and reviewed quarterly"). Policies change rarely — annually at most.
2. **Standard.** Mandatory, specific, measurable requirements implementing a policy ("MFA is required for all administrative access; exceptions require CISO approval and expire within 90 days"). Standards carry the compliance weight and absorb most change.
3. **Procedure / runbook.** Step-by-step how-to owned by the executing team; may change whenever tooling changes, without re-approving the parent policy.
4. **Baseline / guideline.** Configuration templates (CIS-derived images, encryption settings) and optional guidance; version-controlled alongside infrastructure code.
5. **The one-rule test.** Each obligation lives at exactly one level; if a document mixes intent, requirements, and keystrokes, it will be both unapprovable and unmaintainable.

## Lifecycle stages

1. **Trigger and authoring.** New policies start from a trigger — regulation change, incident lesson, audit finding, new technology — with a named author and a named owner (never "the security team"); drafts state scope, effective date, and which roles are accountable.
2. **Review and approval.** Stakeholder review (engineering, legal, HR where people-facing) then approval by the policy owner and CISO, with board-level sign-off for top-tier documents (ISMS policy, risk acceptance policy in ISO 27001 shops). Approval is recorded — who, when, which version.
3. **Publication and communication.** Publish to a single canonical location (intranet portal or version-controlled repo rendered to HTML) with effective dates; remove superseded copies from wikis and onboarding packets so there is exactly one current version anywhere.
4. **Attestation.** Employees acknowledge people-facing policies at onboarding and on material change; privileged-role holders attest to the access-control and acceptable-use standards annually — this is the evidence auditors sample.
5. **Monitoring and control mapping.** Each standard maps to the controls and frameworks it satisfies (SOC 2 CC criteria, ISO 27001:2022 Annex A, NIST CSF 2.0 functions, PCI DSS requirements) in a cross-reference matrix, so one well-governed policy set serves every audit instead of per-framework duplicates.
6. **Exception management.** Deviations are requested against a specific standard, business-justified, risk-assessed, granted with compensating controls, time-boxed (one year maximum is the common ceiling, per university and enterprise practice alike), recorded in an exception register, and re-reviewed at expiry — an exception without an expiry date is a policy amendment nobody approved.
7. **Periodic review.** Every policy and standard gets a scheduled review (annual default; sooner after incidents, reorgs, or regulatory change); review confirms the document still matches practice — the review decision is recorded even when nothing changes ("reviewed, no changes required, next review in 12 months").
8. **Retirement and archival.** Superseded documents are archived with version history retained for audit lookback (align retention with your recordkeeping obligations, commonly 6+ years for HIPAA-governed content) and removed from attestation cycles.

## Operating mechanics that keep it honest

1. **Versioning and changelogs.** Semantic versioning with a dated changelog per document; every approved change is a diff a reviewer can read. Policy-as-code (documents in git, changes via pull request, approval via review) gives you this for free and makes approval evidence automatic.
2. **Ownership as data.** Maintain an owner, approver, last-reviewed date, next-review date, and attestation status per document in a register; drive escalations off next-review dates rather than memory.
3. **Metrics for the GRC review.** Percentage of policies within review date, percentage of workforce attested, open exceptions past expiry (target: zero), average time-to-approve changes, and count of unowned documents — trend these in management review.
4. **Write policies to match practice, then ratchet.** A policy that aspirationally exceeds reality manufactures nonconformities; document current controls, then raise the standard on a planned schedule with remediation tracked.
5. **GRC tooling is optional until it isn't.** A git repo plus a spreadsheet register serves a small company; integrated policy modules (ServiceNow IRM and similar) earn their cost when the document count, framework count, or exception volume makes manual tracking the bottleneck.

## Gotchas

1. **Shelfware is the default failure mode.** If nobody owns the review calendar, the first audit after year one finds stale documents — schedule reviews as recurring tickets the moment a policy is approved.
2. **Duplicates diverge.** Per-framework policy copies (a "SOC 2 access policy" and an "ISO 27001 access policy") drift apart within months; enforce single-source documents with a framework-mapping matrix instead.
3. **Exceptions metastasize.** An exception register without enforced expiry dates converges to "the standard is the exception"; make expiry a hard field and review the register quarterly.
4. **Over-attestation annoys everyone.** Requiring acknowledgment of every minor edit trains employees to click without reading; reserve attestation for material changes and annual cycles.
5. **Practice beats prose in an incident.** After a breach or audit failure, investigators compare what the policy said against logs and tickets — an accurate, modest policy is a defense; an inflated one is evidence of negligence.

## Related

1. **`soc2-evidence-collection-automation.md`.** Attestation records and approval artifacts as audit evidence.
2. **`iso-27001-management-review.md`.** Where policy-lifecycle metrics get tabled in an ISMS.
3. **`data-classification-policy.md`.** A concrete example of a standard that belongs in this hierarchy.
