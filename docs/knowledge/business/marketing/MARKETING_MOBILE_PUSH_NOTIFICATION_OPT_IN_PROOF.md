# Mobile Push Notification Opt-In Proof

## Scope

This control governs the capture, storage, and production of opt-in evidence for marketing push notifications sent to mobile devices and the related web-push surface. It applies to first-party app notifications delivered through the operating-system notification service, to web push delivered through a browser prompt or site-installation flow, and to re-engagement prompts that the operating system treats as new authorization flows. It covers the moment a user grants or revokes permission, the upstream consent that may have authorized the prompt, the operational record that an audit can replay, and the platform-side permission state that must be reconciled with that record.

The governing reference is the FTC Children's Online Privacy Protection Act Rule at 16 CFR Part 312 (the COPPA Rule), which establishes requirements for verifiable parental consent before collecting personal information online from children under 13, and which prescribes specific methods operators may rely on to verify that consent. Where the push audience includes children under 13 or where the operator's product is directed to children, COPPA directly governs the opt-in workflow; even where it does not, COPPA is a useful baseline for what constitutes proof of opt-in.

## Workflow or implementation guidance

The end-to-end opt-in workflow proceeds in six stages.

1. Decide whether to prompt. The marketing team determines, before any prompt, whether the user is in the audience for which opt-in is appropriate (for example, has completed age-appropriate onboarding, has reached a meaningful interaction threshold, or has entered a flow where push is reasonably expected).
2. Capture the upstream consent. If the audience requires parental or guardian consent under COPPA, the operator first obtains verifiable parental consent using a method permitted under 16 CFR 312.5, and records the consent artifact, the method used, and the date.
3. Prompt the user. The application issues a native permission prompt only after the upstream consent exists. The prompt is preceded by an in-app explainer that names the brand, the type of messages the user will receive, the cadence, and an easy way to revoke.
4. Record the user response. The platform returns a grant or denial, and the application records the response, the timestamp, the device and OS version, the app build, the upstream consent identifier, the language of the explainer shown, and the prompt sequence identifier.
5. Sync to downstream systems. The grant or denial is propagated to the messaging platform, the customer-data platform, the suppression list, and any vendor that may receive push identifiers. The propagation is logged with the timestamp and the destination identifier.
6. Revoke on demand. The user can revoke from system settings, in-app settings, or via reply-to-message instructions. Each revocation is recorded the same way as the grant and is propagated within a documented short window.

## Controls

The controls in this workflow are designed to make sure that a real opt-in is in place at the moment a marketing push is sent.

- A record for each opted-in device or browser instance includes the upstream consent identifier, the prompt sequence identifier, the explainer text shown, the timestamp, the platform permission state, the app or site that issued the prompt, and the operator that issued the prompt.
- The same record is preserved for opt-outs and revocations, with the time of revocation and the channel through which it was received.
- Marketing push senders must verify that the recipient's identifier is present in the opt-in register before the message is sent. Devices without an active opt-in are excluded from campaign sends.
- The COPPA boundary is treated as a hard gate: no push notification is sent to a user known to be under 13 unless verifiable parental consent has been recorded under a method permitted by the COPPA Rule.
- The prompt is preceded by context; an immediate native prompt with no in-app explanation is treated as a deficient flow.
- The opt-in record is retained for the duration of the active opt-in and for a defined audit window after the most recent interaction, and is not retained longer than that without a documented basis.
- The suppression list, the customer-data platform, and the messaging platform reconcile against each other on a documented cadence, with discrepancies routed for review.

## Validation evidence

Evidence is collected at the moment of the opt-in and audited periodically.

- Sample opt-in records: device ID, upstream consent identifier, prompt sequence identifier, explainer text, timestamp, IP where available, user agent where available, app version.
- Revocation records: identifier, channel, timestamp, propagation timestamp to each downstream system.
- Operator-level COPPA audit: list of users known to be under 13, the verifiable parental consent artifact for each, the consent method and version, and the prompt sequence used.
- Reconciliation reports between the opt-in register, the messaging platform, and the customer-data platform, listing devices that received messages without an active opt-in.
- Periodic test of the revocation flow: confirm that a test user's revocation blocks subsequent sends within the documented window.

## Failure modes and correction

Common failures include issuing the native permission prompt before the upstream consent exists, prompting without a context screen, retaining permission state on the client without forwarding it to the suppression list, sending pushes to a user known to be under 13 without verifiable parental consent, treating platform permission settings as the only record (which means the revocation evidence is lost when the user reinstalls the app), and failing to propagate revocation quickly enough that a recently opted-out user still receives a campaign.

Correction begins by pausing sends to users whose opt-in record cannot be produced. Each affected push identifier is reconciled with the platform permission state, and any identifier that disagrees with the opt-in register is excluded until the record can be remade. The upstream consent registry is reviewed for under-13 users, and any user whose verifiable parental consent is missing is removed from the audience. The prompt workflow is reviewed to confirm that the in-app explainer is present before the native prompt, that the upstream consent gate holds, and that revocation propagation meets the documented service-level expectation. The root cause entry distinguishes between data defects, prompt-flow defects, and propagation defects, and updates the relevant control.

## Limitations

This control does not decide whether a particular message is "marketing," whether the operator is "directed to children" within COPPA's meaning, whether a particular consent method is verifiable parental consent under 16 CFR 312.5, or whether a foreign data-protection regime applies. It does not address email or SMS consent, which are governed by separate regimes (CAN-SPAM, TCPA, GDPR, CASL, and others). It does not adjudicate competing legal bases for processing such as legitimate interest, contractual necessity, or vital interest. Treat the operational gate as a minimum; counsel-classified regimes may impose additional requirements.

## Canonical sources

- **Primary authority 1 — eCFR, 16 CFR Part 312 (Children's Online Privacy Protection Act Rule):** [https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-312](https://www.ecfr.gov/current/title-16/chapter-I/subchapter-C/part-312)
- **Primary authority 2 — Federal Trade Commission, Complying with COPPA (frequently asked questions):** [https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions](https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions)
