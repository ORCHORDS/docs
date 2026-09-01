# Support Outage Status Page Refresh Governance

## Scope

This article governs how the support desk governs the refresh of an outage status page during an incident. The status page is the public record of an ongoing incident; it carries the affected services, the start time, the current state, the next update window, and any workarounds the customer can apply. The scope covers every refresh action: the initial publication, every subsequent update during the incident, the resolution notice, and the post-incident review. It does not cover the underlying incident response (which is owned by the engineering team) and does not cover the customer-side notification (which is owned by the communications team).

The discipline follows the incident communication practice in ITIL 4, where the status page is one of several communication channels and the customer expectation is a consistent, timely, accurate record. The refresh cadence is set by the incident severity and the customer expectation, not by the engineering team's internal reporting cadence.

## Workflow or implementation guidance

The refresh workflow begins at incident declaration. The incident commander declares an incident and assigns an incident manager. The incident manager opens a status page entry and populates the affected services, the start time, the current state (investigating, identified, monitoring, resolved), and the next update window. The status page entry is reviewed by the communications lead before it is published.

The next update window is a commitment. It is the time by which the status page will be refreshed again, regardless of whether the underlying state has changed. A status page that is silent beyond its update window is a customer-trust failure even if the underlying state is unchanged. The incident manager sets the window based on the incident severity: a critical incident has a short window (for example, fifteen or thirty minutes), a high incident has a medium window (for example, one hour), a medium incident has a longer window (for example, two hours).

Each refresh follows a defined template. The template has placeholders for the current state, the affected services, the impact observed, the next update window, and any workarounds. The template is filled in by the incident manager and reviewed by the communications lead before publication. The template is enforced at the publishing tool: a refresh that lacks a required field cannot be published.

The resolution notice follows a similar discipline. The resolution notice states that the incident is resolved, summarises the impact, and points the customer to the post-incident review if one is planned. The resolution notice is published only when the engineering team has confirmed the resolution and the monitoring has held for a defined window.

## Controls

Three controls protect the status page. The first is the update-window enforcement: a status page entry that is approaching its window receives an automated alert to the incident manager. The second is the template enforcement: a refresh that lacks a required field is rejected at the publishing tool. The third is the audit: a periodic review confirms that every refresh was published on time, that every refresh matched the template, and that the resolution notice was preceded by a holding window.

A separate control protects against the unauthorised publication. A status page entry that names a third party, that discloses a security-relevant detail, or that commits the organisation to a specific remediation timeline is reviewed by a second agent before publication. The review is logged.

## Validation evidence

Validation evidence is collected continuously. The status page log records every refresh, the timestamp, the actor, and the template fields. The customer-facing timeline is compared against the internal log to confirm that every internal refresh was published. A periodic tabletop exercise tests the cadence: a synthetic incident is declared and the status page is observed to refresh at the committed windows.

## Failure modes and correction

The most common failure is the update window being missed. The incident manager is engaged in the underlying response and forgets the status page. The correction is the automated alert and the escalation when the window is breached.

The second most common failure is the template being filled with internal jargon. The status page is for the customer, not for the engineering team. The correction is the communications lead review and the periodic audit of customer-facing language.

The third most common failure is the resolution notice being published before the holding window. The engineering team confirms the resolution, the incident manager publishes, and the underlying state regresses. The correction is the holding window and the monitoring check before the resolution notice is published.

## Limitations

The refresh discipline assumes that the publishing tool supports templates and update-window alerts. Where the tool is a static page that requires manual updates, the discipline degrades; the incident manager must remember the cadence and the template. The organisation should confirm that its tool supports the automated affordances before it commits to the discipline.

The discipline also assumes that the customer expectations are bounded. Where the customer base is global, the update window may be inappropriate for some time zones; a 15-minute window in the middle of the night for one region is a reasonable cadence for another. The discipline should be applied with awareness of the customer geography.

## Canonical sources

- AXELOS, ITIL 4 Incident Management Practice (publisher and title only; AXELOS publications are referenced via https://www.axelos.com/resource-hub/case-studies/itil-4-foundation).
- NIST SP 800-53 Rev. 5, System and Information Integrity control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/