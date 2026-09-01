# Retargeting Pixel Consent Proof

## Scope

This control governs the capture, storage, and production of consent for retargeting pixels, advertising tags, conversion trackers, and similar on-page or in-app measurement and audience-building tools. It applies to first-party pixels deployed on owned web properties, to pixels deployed by advertising platforms on partner properties, to server-side conversion APIs, to on-page tag managers that load additional downstream vendors, to in-app SDKs that perform similar functions, to data clean-room integrations, and to any external recipient that receives identifiers or event data tied to a user.

The governing reference is the IAB Europe Transparency & Consent Framework v2 (TCF v2), which defines how participating vendors, publishers, consent management platforms, and integrated advertising systems store, transmit, and act on the consent string. The TCF v2 consent string encodes the purposes for which the user has consented, the features in use, the vendor identifiers that are authorized, and the publisher restrictions relevant to the audience. This control treats compliance with the TCF v2 specification, where applicable, as the operational baseline for consent proof across the digital advertising chain.

## Workflow or implementation guidance

The retargeting consent workflow proceeds in six steps.

1. Surface the consent tool. A consent management platform surfaces a notice and a choice on each property where advertising measurement or audience building occurs. The notice is layered: a default state with no personalization, an information layer explaining the categories of processing, and a choices layer with granular toggles.
2. Capture the choice. The CMP collects the user choices, transmits them in the TCF v2 consent string format, and stores a signed record of the specific UI shown, the version, the timestamp, the IP and user agent, the language, and the categories the user accepted or refused.
3. Stash the consent string. The string is exposed on the page for vendors to read. The string is also stored server-side alongside the publisher-restrictions and the CMP version. The publisher's downstream identity, the publisher country, and the feature toggles are part of the stored record.
4. Gate the pixel or tag. Vendors read the TCF v2 consent string before loading or processing. Where the string does not authorize the declared purposes, the vendor is blocked. Purpose 1 (store and/or access information on a device) and the legitimate-interest or consent basis declared for the purpose are the operational gate.
5. Transmit signal to recipients. Where consent is granted to specific vendors, only those vendors receive downstream identifiers or events. Conversion APIs and clean rooms are configured to honor the string on a per-request basis.
6. Honor change and revocation. A user revisiting the consent tool, exercising choice, or revoking consent triggers a refreshed string. Vendors must reread the string on each interaction or on refresh; the CMP must update both the page stash and the stored record, and the publisher-restrictions must be enforced downstream.

## Controls

The controls in this workflow address the integrity of the consent string and the chain of trust through which it is read.

- The CMP version, the policy version (TCF v2.x), and the feature toggles are recorded in the audit log alongside the user choices.
- A vendor list is maintained. Only vendors listed in the TCF v2 Global Vendor List with a valid signal pass the gate; unlisted vendors cannot rely on TCF v2 alone and must collect consent through a different mechanism.
- The TCF v2 purposes for which consent is required (for example, purposes 1, 3, 4) are mapped to internal audience segments, retargeting lists, and conversion events. Each mapping has an owner.
- The publisher restrictions in the consent string are honored. A vendor that receives "no" for a purpose is excluded from the audience and from the event payload.
- Server-side reconciliation matches the page-side string with the stored record; mismatches are treated as errors that block sends until reconciled.
- The stored record is retained at least through the audit window and not used for unrelated purposes (such as modeling or training) without a separate basis.
- Vendors with insufficient scope (no TCF v2 signal, or no purpose coverage) are routed through a separate consent capture rather than being allowed to piggyback on the TCF v2 string.

## Validation evidence

Evidence is collected at consent capture, on every interaction, and on demand.

- Sample consent records: CMP version, policy version, UI version, language, timestamp, IP and user agent where available, the purposes and vendors the user accepted, the publisher restrictions.
- Server-side reconciliation report: page-side string vs server-side string per session, listing mismatches and remediation.
- Vendor activation log: for a sampled session, the list of vendors loaded, the purposes each vendor operated under, and the requests blocked because of missing consent.
- Retargeting audience membership log: source event, consent string version, vendor restriction set, and the downstream recipient that joined the audience.
- Change log: consent strings reissued within the same session and the refresh event that triggered them.

## Failure modes and correction

Common failures include silently upgrading the TCF v2 policy version without re-collecting consent, accepting vendor claims of "TCF v2 compliant" without checking the vendor list and signal at load time, using a single consent string across vastly different audiences, treating publisher restrictions as advisory, modeling or training on the consent string or on identifiers tied to it, and continuing to send events to vendors who have been removed from the vendor list or whose signal has lapsed. Other failures include serving a consent notice that is too faint for the audience or so prominent that it constitutes dark patterns.

Correction begins with the user-level remediation: identify the sessions where the consent defect occurred, stop sending events for those sessions, and refresh the campaign's audience to reflect only the corrected consent population. The CMP and policy version are re-evaluated, and the affected vendor is re-tested under the updated configuration. Where the failure was systemic, the publisher restriction enforcement and the vendor gating are re-validated, with a regression test added to the workflow. The root cause entry identifies the layer that produced the defect and updates the relevant control. Where the defect raises a regulatory question, the matter is referred to counsel rather than adjudicated operationally.

## Limitations

This control does not decide whether a specific purpose or feature is "consent" or "legitimate interest" under EU or member-state law, whether the publisher is required to use a CMP at all, whether particular processing requires opt-in under ePrivacy or national rules, or whether a downstream contract's lawful-basis language complies. It does not address consent for analytics, A/B testing, or personalization that does not rely on advertising-system identifiers. It does not replace a data-protection impact assessment, transparency notice, or cookie-policy review. Where a jurisdiction has stricter rules than TCF v2 contemplates, that jurisdiction's rules take precedence and require separate controls.

## Canonical sources

- **Primary authority 1 — IAB Europe, TCF for Vendors:** [https://iabeurope.eu/tcf-for-vendors/](https://iabeurope.eu/tcf-for-vendors/)
- **Primary authority 2 — IANA, TCF Parameters (consent string specification assignment):** [https://www.iana.org/assignments/tcf-parameters/tcf-parameters.xhtml](https://www.iana.org/assignments/tcf-parameters/tcf-parameters.xhtml)
