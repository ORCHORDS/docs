---
title: "Marketing Data Retention"
owner: "Marketing Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Marketing Data Retention

## Purpose

Marketing data — lead records, campaign responses, audience segments, behavioural profiles, suppression lists, vendor reports — accumulates quickly. Without a deliberate retention discipline, data is kept longer than necessary, increasing privacy exposure, security risk, and storage cost. This article establishes the per-purpose retention schedule, the verification process for deletion, the handling of suppression lists, and the recertification cadence that govern marketing data throughout its lifecycle. The objective is to keep data only as long as it serves a documented purpose and to delete it verifiably when that purpose ends.

## Scope

This article applies to every category of marketing data, whether held by the Marketing organisation, by a vendor on the organisation's behalf, or by a co-marketing partner under a contractual arrangement. It covers first-party data, second-party data, third-party data, inferred data, and pseudonymised data. It applies to data in production, in backup, in archive, and in analytics environments. It does not apply to data held under a separate legal hold; legal holds override the retention schedule.

## Requirements

- Marketing MUST publish a retention schedule that names each data category, the purpose of retention, the lawful basis, the maximum retention period, the deletion method, and the responsible owner. The schedule is the authoritative reference.
- The retention period MUST be the minimum necessary to serve the documented purpose. Convenience, future-proofing, or speculative re-use are not acceptable justifications for extended retention.
- Data MUST be deleted or irreversibly pseudonymised at the end of the retention period. The deletion MUST be verifiable: the record of deletion is itself retained for the period required by the audit policy.
- Backup copies of deleted data MUST be aged out according to the backup retention policy; the backup retention policy MUST NOT extend the marketing retention period for the underlying data.
- Marketing MUST distinguish between suppression lists and marketing records. Suppression lists (do-not-contact, do-not-target) MUST be retained for as long as the suppression is in effect and for a documented tail period after the suppression reason ends, to prevent re-contact from a refreshed dataset.
- Marketing MUST honour data-subject deletion, rectification, and restriction requests within the time limits set by applicable law; the technical capability to act on these requests MUST be in place for every category of data.
- Where data is retained for analytical or statistical purposes, it MUST be pseudonymised or aggregated to the extent compatible with the analytical purpose.
- Vendor-held data is subject to the same retention period as data held internally; the contract MUST require deletion or return at the end of the period and MUST permit audit.
- Marketing MUST maintain a recertification register that confirms the retention schedule for each category of data is still appropriate; recertification occurs at least annually and after any change in law or policy.
- Data older than the maximum retention period MUST be quarantined and then deleted; a quarantine stage reduces the risk of accidental re-use during the deletion lag.
- Where data is shared with a co-marketing partner, the sharing agreement MUST specify the retention period, the deletion obligation, and the audit right; the Marketing Lead is accountable for confirming compliance.

## Workflow

1. The retention schedule is reviewed annually by the Marketing Lead, the Privacy function, and the Legal function; updates are versioned.
2. Daily and weekly jobs scan each data store for records past their retention period; records are flagged for deletion or quarantine.
3. The owner of each category confirms the deletion list before execution; ambiguous cases are escalated.
4. Deletion is executed and the deletion record (timestamp, scope, method) is stored in the audit log.
5. Backup systems run their retention cycle; the storage team confirms that deleted records do not reappear in restored backups.
6. At recertification, the schedule is reviewed and any categories whose retention rationale has changed are amended.

## Controls

- The retention schedule is published and versioned; each version has an owner and a "next review" date.
- Deletion jobs run at a cadence sufficient to clear aged records within the retention period plus a small grace window.
- Audit logs of deletion are immutable and retained for the period required by the audit policy (typically seven years).
- Annual recertification is performed jointly by Marketing, Privacy, and Legal; the recertification record is filed.

## Canonical sources

- European Commission, "Regulation (EU) 2016/679 (GDPR) — Article 5(1)(e) Storage limitation" — https://eur-lex.europa.eu/eli/reg/2016/679/oj
- Information Commissioner's Office (UK), "Storage limitation" — https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/data-protection-principles/
- California Office of the Attorney General, "CCPA — Data Retention and Disposal" — https://oag.ca.gov/privacy/ccpa
- International Organization for Standardization, "ISO/IEC 27001:2022 Information security, cybersecurity and privacy protection" — https://www.iso.org/standard/27001