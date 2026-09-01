---
title: "Remote Session Governance"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Remote Session Governance

## Purpose

Govern the conditions under which support personnel initiate a remote-support session — a screen-sharing, remote-control, or remote-shell session on a customer device — so that the customer's autonomy, privacy, and the integrity of the support process are preserved.

## Scope

This article covers remote sessions initiated at the customer's request for the purpose of troubleshooting, training, configuration help, or guided recovery. It covers sessions conducted via approved screen-sharing tools, attended remote-access tools, remote-shell or remote-terminal tools, and similar capabilities that allow the agent to view or operate the customer's device. It does not govern the operation of company-owned infrastructure, which has separate change-management and access rules.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Consent

Before any remote session begins, the agent MUST obtain explicit, recorded consent from a person who has authority over the device and its contents. Consent MUST be obtained in the language the customer understands, MUST describe the purpose of the session, the type of access (view, view-and-control, terminal, file transfer), the approximate duration, the ability to end the session at any time, and the recording policy (whether the session will be recorded, who can access the recording, how long it is retained, and how the customer can request deletion consistent with policy and law). Consent MUST be renewed if the session changes in material way — for example, switching from view-only to view-and-control, expanding scope to additional devices, or extending significantly past the originally stated duration.

The agent MUST NOT proceed without recorded consent. Silence, default-on settings, or pre-checked boxes are not consent. Consent MUST be revocable; the customer MUST be able to end the session at any time and the agent MUST cease activity promptly on request.

## Scope restrictions

The agent MUST operate within the approved scope. The agent MUST NOT:

- access files, applications, browser tabs, message histories, photos, or other content outside the stated troubleshooting purpose;
- browse personal folders that are not relevant;
- read private messages, email, or notes unrelated to the issue;
- install software, certificates, browser extensions, or configuration changes that the customer has not approved;
- copy customer files to the agent's workstation, to a personal device, or to an unapproved storage location;
- leave persistent remote-access tools installed beyond what is needed for the immediate case.

When the issue requires touching a sensitive area (for example, payment information, authentication factors, identity documents, medical or health data), the agent MUST pause the session, re-confirm consent for that specific area, and consider whether the work should be referred to a specialist flow.

## Recording

If the session is recorded, the customer MUST be told before recording begins, MUST be told who can access the recording, and MUST be told how long the recording will be retained. Recordings MUST be classified and retained according to the data they contain, not according to the lowest-classification segment. Recordings that capture payment data, authentication factors, or other highly sensitive content MUST be redacted, access-restricted, or avoided entirely in favor of text-based alternatives. Recordings MUST NOT be used for training or quality review beyond what the consent covers.

## Audit trail

Every remote session MUST be logged with at minimum:

- the case identifier and the customer identifier;
- the agent identity and, where relevant, the joined observer (for example, a quality reviewer joining with the customer's consent);
- the tool and tool version;
- the session start and end times;
- the consent record reference;
- a high-level description of the actions taken (commands run, configuration changes, files transferred);
- any anomaly or interruption, including disconnects, scope expansions, or session-ending events;
- a reference to any recording and its classification.

Audit logs MUST be reviewable for the documented retention period and MUST be sufficient to reconstruct, at a coarse level, what the agent did during the session.

## Post-session evidence

After the session, the agent SHOULD provide the customer with a written summary of what was done, including any settings changed, software installed or removed, accounts accessed, and any credentials or factors that were used or rotated during the session. The summary SHOULD be written in plain language and SHOULD include guidance on how to verify the changes. If the agent installed any persistent tool, the summary MUST include removal steps.

## Failure and incident handling

If the session is interrupted unexpectedly, if the agent loses visibility into whether the customer remains present, or if the customer asks the agent to stop, the agent MUST terminate the connection promptly. If the agent observes content that suggests a security, privacy, or safety concern (for example, suspected compromise, harassing content, indications of self-harm), the agent MUST follow the relevant escalation rather than continuing to view the content. The session MUST be reported through the incident-management path where the trigger is material.

## Canonical sources

- NIST SP 800-46 Rev. 2, *Guide to Enterprise Telework, Remote Access, and Bring Your Own Device (BYOD) Security*, https://csrc.nist.gov/publications/detail/sp/800-46/rev-2/final
- ISO/IEC 27001:2022, Information security management — Requirements, https://www.iso.org/standard/27001
- NIST SP 800-53 Rev. 5, *AC-17 Remote Access* and *SC-15 Collaborative Computing Devices*, https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final
- European Data Protection Board, *Guidelines 05/2020 on consent under Regulation 2016/679*, https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-052020-consent-under-regulation-2016679_en
