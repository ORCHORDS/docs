# Support Incident Customer Timeline Accuracy

During a service incident, customers rebuild their trust from two artifacts: what the desk tells them, and whether what they were told matches what actually happened. A timeline that shifts, an "estimated resolution" that passes in silence, or a post-incident summary whose clock disagrees with the customer's own records does more damage than the outage itself. This article governs the accuracy of customer-facing incident timelines: clock discipline for the published record, update commitments that are honored or corrected, and the correction notice when a published statement turns out wrong.

## Scope

This article covers customer-facing communications during and after service incidents: the incident timeline published to status pages, incident tickets, and direct notifications; the timestamps and timezones used; update cadence commitments; and corrections to previously published statements. It applies to major and minor incidents that carry any customer-visible communication.

It does not cover internal incident command, root-cause analysis methodology, or regulator notification duties, though a wrong customer timeline often creates those obligations. It assumes an incident process exists that assigns ownership of communications.

## Workflow or implementation guidance

Clock discipline comes first because every later artifact depends on it:

1. One clock of record. All published timestamps derive from a single clock of record, recorded in UTC. Local-time renderings may be shown alongside, clearly labeled with offset, but UTC is the canonical value everywhere, and conversions are done by tooling rather than by whoever is typing the update.
2. Event vocabulary. The timeline uses a fixed set of event states (detected, confirmed, mitigating, monitoring, resolved, closed) with written definitions agreed before any incident. Ad-hoc states invented mid-incident ("mostly fixed") are edited to the standard vocabulary or omitted, because a state that cannot be defined cannot be audited.
3. Boundary timestamps. Each state change gets its timestamp from the system that observed it (monitoring alert, change completion, verification run), not from the moment a communications owner typed it. Where a boundary must be backfilled, the backfill is marked internal and does not alter the published value without the correction process below.
4. Detection-versus-onset honesty. The timeline states detected time as detected time; where evidence later shows the impact began earlier, the customer-facing record gains a note of the earlier onset with its evidence basis, rather than quietly rewriting the detected time.

Update commitments: at incident declaration, the desk commits to an update interval (for example, every 30 or 60 minutes for high-impact) and honors it in one of two ways: a substantive update, or a holding update that states what is being done and when the next update comes. A missed interval is itself a defect: the next update acknowledges the gap and its length; silence past the interval is prohibited.

Estimates: resolution estimates are labeled as estimates with the basis ("restoration in progress; estimate 45 minutes") and are recomputed at each update. When an estimate passes without resolution, the update that follows opens by acknowledging the missed estimate before saying anything else. Estimates are never published without a stated next-update time, because the estimate-plus-commitment pair is what lets a customer plan.

Resolution: a state moves to resolved only on verification evidence (checks passing, traffic restored, error rates at baseline), not on hope or on the fix merely being deployed. The resolved notice states what customers should observe and what to do if they still see impact, with a reopen path that is trivially easy to use.

Post-incident summary: within the published commitment window (commonly a few business days for high-impact incidents), the summary publishes the timeline in UTC with the standard states, impact description by service and region, cause in customer-appropriate language, and remediation items with owners. The summary's timestamps must match the live timeline as published, except where the correction process below was invoked, in which case the correction is visible in the summary.

Correction notices: when a published statement was wrong (wrong time, wrong scope, a resolved state later shown premature, an estimate presented as fact), the correction is appended, not overwritten. The record shows: the original statement, what was wrong, the corrected statement, and when the correction was issued. Status-page tooling that supports only overwrite is supplemented by dated entries, because a silently edited timeline teaches customers to screenshot everything.

## Controls

- UTC-canonical rule: publishing tooling stores and displays the UTC value; local rendering is display-only.
- Standard-state gate: the update template accepts only standard states; free-state entries require communications-owner override, logged.
- Update-interval monitor: during an active incident, an automated check alerts when the committed interval passes without an update; the alert goes to the incident commander, not only the communications owner.
- Verification-before-resolved: the resolved transition requires a linked verification artifact (check output, metric snapshot) in the incident record.
- Correction ledger: all post-publication edits to timeline entries are recorded in an append-only ledger with the original text preserved.
- Summary reconciliation: before publishing, the post-incident summary is diffed against the live timeline and the correction ledger; any mismatch blocks publication.

## Validation evidence

Evidence the discipline holds: the interval-compliance record for each incident (updates due, delivered on time, late, with lateness); the verification artifacts linked to each resolved transition; the correction ledger with its entries and their reasons; summary reconciliation diffs; and a periodic audit that takes a sample of incidents and compares the published timeline against system-of-record timestamps (monitoring alerts, change records), reporting discrepancies. Customer-side corroboration, such as complaint volumes citing contradictory times or screenshots of altered entries, is tracked as a harm signal, with zero tolerance for uncorrected discrepancies.

## Failure modes and correction

The silent overwrite is the defining failure: an entry is edited to look right, customers notice the mismatch with their own records, and trust in the status page collapses. Correction: append-only ledger, visible correction entries, and tooling that cannot quietly rewrite.

The eternal estimate is second: a resolution estimate passes, another is issued with no acknowledgment, and customers learn the estimates are decorative. Correction: the missed-estimate acknowledgment rule in the update template, enforced by review before posting.

Premature resolution is third: the fix is deployed, the state flips to resolved, and a customer segment still sees impact; reopening then requires another declaration cycle. Correction: verification-before-resolved with evidence, plus a lightweight reopen path from the resolved notice.

Timezone confusion is fourth: an update typed during a handoff between regions carries an ambiguous or wrong local time, and customers misjudge the window. Correction: UTC-canonical tooling and prohibition on hand-typed local timestamps.

Backfill drift is fifth: internal review moves a boundary time, the summary publishes the new time, and the live timeline still shows the old one. Correction: the summary reconciliation diff, which exists precisely to catch this.

## Limitations

Customer-facing timelines are less detailed than internal ones by design; accuracy here means the published subset is true, not that it is complete. Detection time depends on monitoring coverage, so the honest timeline can still understate customer-experienced onset until evidence arrives. Correction visibility is bounded by platform: some channels (email, social) cannot append, and the correction must be reissued as a new message with a reference to the original. During severe incidents, communications capacity is itself a constrained resource, and the holding-update pattern exists to keep the commitment affordable; it is a floor, not a substitute for substance.

## Canonical sources

- NIST SP 800-61 Rev. 3, Incident Response Recommendations and Considerations for Cybersecurity Risk Management, https://csrc.nist.gov/pubs/sp/800/61/r3/final
- IETF RFC 3339, Date and Time on the Internet: Timestamps, https://www.rfc-editor.org/rfc/rfc3339.html
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
