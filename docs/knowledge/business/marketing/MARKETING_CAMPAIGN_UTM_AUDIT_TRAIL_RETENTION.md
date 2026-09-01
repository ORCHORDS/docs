# Campaign UTM Audit Trail Retention

## Scope

This control governs how long, where, in what form, and under what access discipline the marketing organization retains the records that explain a UTM-tagged campaign. It applies to records describing each UTM-tagged URL: the original UTM parameters, the campaign plan that produced them, the destination URLs and their deployed copies, the approvals captured at launch, the analytics outputs produced during and after the campaign, and the corrective actions taken on the campaign record itself. It applies to paid search, paid social, owned social, email, display, programmatic, affiliates, partners, QR codes, influencer-distributed links, lifecycle automation, and any other channel that uses UTM or analogous tagging parameters.

The governing reference is ISO/IEC 27001:2022 (Information security, cybersecurity and privacy protection — Information security management systems — Requirements), which sets out requirements for an information security management system including controls for record retention, access control, and audit trail integrity. An audit trail is not the same as a business record: a business record is the evidence of what was done; an audit trail records the chain of custody, the access events, and the integrity checkpoints for the records.

## Workflow or implementation guidance

The UTM audit trail retention workflow proceeds in six steps.

1. Define the record set. The record set includes (a) the request ticket that produced each tagged URL, with the taxonomy fields, audience destination, and channel; (b) the generated URL or set of URLs; (c) the test evidence at launch; (d) the deployed-artifact snapshot; (e) the change log of any parameter corrections or platform rewrites during the campaign; (f) the post-campaign archival event; and (g) the access log for who read, exported, or modified the record.
2. Classify and protect. Each record is classified (for example, internal, restricted, or confidential) and protected accordingly. UTM parameters themselves should not contain personal data or secrets; records about the campaign (the requestor, the approvals, the change history) deserve a baseline level of access control consistent with the organization's information classification scheme.
3. Store with integrity protection. Records are stored in a system that supports retention, immutability of completed records (or, where immutability is not feasible, a documented integrity-protection mechanism such as signed snapshots or hash chains), and basic retrieval for audit.
4. Set retention horizons. Different kinds of records have different retention horizons: the campaign plan may live longer than the URL itself; the URL is preserved for as long as analytics that depend on it is retained; the analytics records live as long as financial, tax, or contractual obligations require. The retention schedule is documented and reviewed.
5. Disposition on schedule. When the retention horizon is reached, records are disposed. Personal data within the records is removed or anonymized. The disposition event itself is logged.
6. Recoverability test. The audit trail is exercised periodically: given a campaign identifier, the team can produce the original tagged URL, the deployed URL, the launch approvals, the change log, and a representative analytics output for the campaign window.

## Controls

The controls in this workflow are designed to make UTM records usable as evidence, not as write-only memory.

- The record set is defined and documented. A campaign record is not "complete" until all defined record items are present and linked.
- Access to the record is logged. Read-only exports are recorded; modifications are recorded and approved.
- Records that must be retained for financial, tax, regulatory, or contractual reasons are tagged with their disposition date and reason.
- Integrity protections prevent silent editing. Where the system supports immutability of completed records, that property is used; otherwise, a documented integrity-protection mechanism is in place.
- Personal data in records is minimized: UTM parameters should not contain personal data, but if they do, that field is treated as personal data for the retention schedule.
- Recovery time and recovery point for the audit trail are documented and tested.
- Disposition is performed at the scheduled time, not paused indefinitely.

## Validation evidence

Evidence is collected periodically and on demand.

- A sample audit-trail replay: a campaign identifier -> original tagged URL -> approval snapshot -> deployed URL -> analytics snapshot -> disposition record.
- Access logs for the audit-trail system: who read what, when, and why.
- Retention schedule for UTM audit records and the corresponding ticker showing each type's next scheduled disposition.
- Disposition log: records retired, method of disposition, confirmation that no unauthorized copies remain.
- Periodic recoverability test: a randomized campaign is selected and the full record reconstructed from the audit trail alone.

## Failure modes and correction

Frequent failures include treating analytics dashboards as durable records (they are mutable and may be reset), storing URL parameters without storing the request or approval, mixing personal data into UTM parameter values without a documented retention schedule for that data, retaining records without a documented purpose indefinitely, allowing campaign managers to delete records at will, and storing approval evidence in email threads or chat instead of the campaign record. Other failures include relying on a vendor's analytics warehouse as the source of truth for an organization's own retention horizon.

Correction starts by identifying the affected records. Where records were stored without integrity protection, they are now treated as conjectural, and the campaign is reconstructed from the strongest available secondary evidence with a note in the audit trail. Where records were deleted prematurely, the deletion is logged as an incident, the root cause is identified, and the access control is updated. Where the retention schedule was not followed, the schedule is re-issued, the operational queue for disposition is reactivated, and the disposition work is executed according to the updated schedule. A corrective action is added to the audit-trail playbook.

## Limitations

This control does not determine what counts as "personal data" under GDPR or analogous regimes, what constitutes a "legitimate" purpose for retention, or how long financial, tax, or sector-specific records must be kept. It does not by itself produce UTM values that are consistent with campaign naming conventions, taxonomy discipline, or analytics reporting; it only retains the record of those values once they exist. It does not adjudicate which records may be shared with regulators, courts, or counterparties and under what legal process; it provides the operations by which records are produced once a legal determination has been made. It assumes an information classification scheme already exists in the organization.

## Canonical sources

- **Primary authority 1 — ISO/IEC 27001:2022, Information security, cybersecurity and privacy protection — Information security management systems — Requirements:** [https://www.iso.org/standard/27001](https://www.iso.org/standard/27001)
- **Primary authority 2 — ISO Online Browsing Platform (27000 family index):** [https://www.iso.org/obp/ui/#iso:std:iso-iec:27001:en](https://www.iso.org/obp/ui/#iso:std:iso-iec:27001:en)
