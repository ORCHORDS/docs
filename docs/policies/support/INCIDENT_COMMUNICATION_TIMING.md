---
title: "Incident Communication Timing"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Incident Communication Timing

## Purpose

Set the timing discipline for outbound customer communications during an incident — first notice, cadence, closure, and follow-up — so that customers can rely on the company for accurate, timely information and so that support agents are not improvising updates under pressure.

## Scope

This article covers customer-facing communications about incidents that affect availability, security, privacy, integrity, or major functionality. Incidents range from a transient degradation visible to a single queue to a region-wide outage or a confirmed security incident with regulatory exposure. The article applies to all outbound channels the company uses to reach customers about the incident, including email, in-product messaging, status pages, public statements, and direct agent responses.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## First notice

A first notice SHOULD be issued as soon as the company can do so without overstating certainty. The first notice MUST NOT wait for full root cause if waiting would leave affected customers without an authoritative point of contact for an extended period. The first notice SHOULD include the customer-visible impact, the affected products or services, the time the impact started (or the best estimate), what customers can do as a workaround if one exists, and where they can find updates. The first notice MUST NOT speculate beyond what is known, MUST NOT minimize impact, and MUST NOT assign blame prematurely.

When an incident is also a suspected security or privacy event, the first notice SHOULD be coordinated with the security and privacy functions before public release. The communications team SHOULD ensure that the first notice is compatible with any subsequent regulator notification timeline without backdating or modifying the customer-facing message.

## Cadence

Updates SHOULD be issued at a regular cadence that matches the severity and duration of the incident. Severities defined elsewhere in the incident-response framework SHOULD drive a corresponding update cadence. The cadence SHOULD be made explicit at the time of the first or second update so that customers can plan around it. Cadence MUST be maintained even when there is no new technical information; an "investigating, no change" update is preferable to silence, and silence beyond the documented cadence MUST itself trigger an escalation within the communications function.

Updates MUST NOT contradict each other. If new information materially revises the picture, the update SHOULD explicitly state the revision, the prior position, and the reason. Customers and agents SHOULD be able to reconstruct the public timeline from the published notices.

## Closure

A closure notice SHOULD be issued when the customer-visible incident is fully resolved or when the incident enters a long-tail phase with normal operation restored and follow-up scheduled. The closure notice SHOULD include the resolution summary at the level of detail appropriate for customers (and at a separate, more detailed level for internal audiences and regulators where required), the time of resolution, the residual risks customers should know about, and the follow-up plan. The closure notice SHOULD NOT be issued before the team that owns the incident confirms resolution, and SHOULD be coordinated with the post-incident review so that customers and internal stakeholders receive consistent information.

## Follow-up

After closure, a follow-up communication SHOULD be sent within the timeframe defined by the incident-severity framework. The follow-up SHOULD cover root cause at the appropriate level of detail, remediation already in place, planned remediation, and any actions the customer should take (for example, credential rotation if the incident exposed credentials). The follow-up MUST NOT contain promises that have not been agreed with the engineering owner, and MUST be approved by the same chain that approves the closure notice.

## Quality of customer-visible language

Notices MUST be written in plain language, MUST be accessible to screen readers and to translation tools, MUST be available in the languages the company has committed to support for incident communications, and MUST be reviewable before publication by an editor who has not been deeply embedded in the incident response. Notices SHOULD avoid jargon that excludes non-technical customers and SHOULD be screened for statements that could later be used to deny customer remedies (for example, "no data was affected" before that fact is established).

## Discipline for the support function

Support agents MUST direct customers to the authoritative incident notice rather than improvising a different account. Agents MUST NOT release information that has not been published through the communications function. When a customer asks for information not yet published, agents MUST acknowledge the gap, provide a timeline if available, and route the question to the communications owner if appropriate. Agents MUST record the questions customers ask during the incident so that the communications function can address them in subsequent updates.

## Canonical sources

- NIST SP 800-61 Rev. 3 (Draft), Computer Security Incident Handling Guide, https://csrc.nist.gov/publications/detail/sp/800-61/3/draft
- ISO/IEC 27035-1:2023, Information technology — Information security incident management, https://www.iso.org/standard/78973.html
- UK NCSC, *Incident management*, https://www.ncsc.gov.uk/section/about-this-website/incident-management
- Web Content Accessibility Guidelines (WCAG) 2.2 emergency-communication guidance, https://www.w3.org/TR/WCAG22/
