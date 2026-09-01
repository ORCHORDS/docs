---
title: "Support Outage Cross-Team Coordination"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Support Outage Cross-Team Coordination

## Purpose

Define the coordination protocol between support and engineering during an outage, including the bridge, the named roles, the status-page discipline, the customer-communications cadence, and the after-action review, so that customers and internal stakeholders receive consistent, timely information and the technical response is not impeded by improvised support process.

## Scope

This article covers the period from the moment an outage is declared (or the moment a probable outage is identified and cross-team coordination begins) through closure, follow-up communications, and the post-incident review. It covers outages that affect availability, performance, integrity, or major functionality of a customer-facing product or service. It does not change the incident-response procedure owned by engineering; it sets the support-side obligations and the points at which support and engineering must interact.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Bridge protocol

A named bridge (voice or chat, with a written log) MUST be established when support and engineering need to coordinate in real time. The bridge MUST have:

- a designated incident commander from engineering who owns the technical response;
- a designated support coordinator who owns the customer-facing response;
- representatives from the affected product, infrastructure, security, and communications functions as needed;
- a shared log of decisions, with timestamps and authors;
- a defined handoff plan when the bridge stands down (so that on-call coverage remains intact).

The bridge MUST NOT be used as a substitute for the incident-management system of record. Decisions reached on the bridge MUST be entered into the incident record, with a clear link to the bridge log. The bridge MUST have an end condition so that it does not become a permanent room for routine work.

## Named roles

The support coordinator MUST be named in the incident record and MUST have the authority to make support-side decisions within the boundaries of this and related policies (for example, refunds, communications timing, escalation changes). The coordinator SHOULD be the single point of contact between support and engineering for the duration of the incident, so that engineering is not negotiating with multiple support agents and support is not negotiating with multiple engineers. Role transitions MUST be recorded in the incident record with a hand-off summary.

The coordinator SHOULD NOT also be the lead engineer or the engineering commander; the separation preserves the customer focus in the support-side response and the technical focus in the engineering-side response.

## Status-page discipline

The status page MUST be the authoritative customer-facing source of truth during the outage. It MUST be updated at the cadence required by the incident-communications policy and at minimum whenever there is a material change in customer-visible impact or resolution. Status-page updates MUST be approved by the support coordinator or by a designated approver before publication, and MUST be consistent with the customer-facing communications elsewhere (email, in-product messaging, agent responses). The status page MUST NOT be edited to remove history; the customer-facing timeline is part of the record.

If the incident is also a security or privacy event, the status-page text MUST be coordinated with the security and privacy functions before publication. If the incident has regulator exposure, the timing of public updates MUST NOT pre-empt regulator notification timelines in a way that creates legal risk; the support coordinator and the legal function MUST agree the cadence before each new public update.

## Customer communications during the outage

Customer-facing communications during the outage MUST follow the incident-communications policy (separate article). The support coordinator MUST ensure that the wording, the affected scope, and the workaround advice are consistent across all channels, and that the language used by frontline agents is consistent with the public communications. The support coordinator MUST NOT publish changes that have not been agreed with the engineering commander where the change affects technical claims.

Support agents MUST direct customers to the status page for the authoritative update and MUST NOT improvise conflicting explanations. Agents MUST record the questions customers ask so that the communications function can address them in subsequent updates. Agents SHOULD escalate cases that the standard communications do not address (for example, customers with material financial impact, accessibility needs, or safety concerns) to the coordinator rather than handling them in isolation.

## Refunds, credits, and accommodations during the outage

The support coordinator and the engineering commander SHOULD agree, at the earliest practical point, whether the incident warrants a credit, a refund, a fee waiver, or another accommodation under the documented incident-credit program. Where the program applies, it SHOULD run on a documented list rather than on per-customer discretion, to ensure consistency and to avoid the appearance of favoritism. Where the program does not apply, individual accommodations MUST follow the refund-authority policy. Customers MUST NOT be pressured to forgo a credit in exchange for faster resolution of the underlying incident.

## After-action review

After closure, a post-incident review MUST be conducted with engineering, support, the communications function, and any other involved functions. The review MUST cover the timeline, the bridge decisions, the customer-impact assessment, the status-page and communications cadence, the support-side handling, the agent experience, the customer experience, the lessons learned, and the action items with owners and target dates. The action items MUST include both engineering remediation and support-side improvements (for example, knowledge-base updates, training, policy revisions). Findings SHOULD be aggregated across incidents to identify patterns.

## Audit

The coordination process MUST be auditable. The incident record, the bridge log, the status-page history, the customer-communications history, and the post-incident review MUST be cross-referenced and retained per the records-retention schedule. Audit findings SHOULD feed the support-quality program, the incident-management program, and the cross-team coordination review.

## Canonical sources

- NIST SP 800-61 Rev. 3 (Draft), Computer Security Incident Handling Guide, https://csrc.nist.gov/publications/detail/sp/800-61/3/draft
- ISO/IEC 27035-1:2023, Information technology — Information security incident management, https://www.iso.org/standard/78973.html
- Atlassian, *Incident Handbook* (public summary), https://www.atlassian.com/incident-management/handbook
- Google SRE Book, *Managing Incidents*, https://sre.google/sre-book/managing-incidents/
