# Support Device Telemetry Consent Recording

## Scope

This article governs how the support desk records consent before collecting device telemetry from a customer's device during a support session. Telemetry here means any automated collection of device state, logs, configuration, performance counters, or behavioural traces initiated from the support side. The article does not cover in-product telemetry that runs without the customer's active involvement (which is governed by the product's privacy notice); it covers only the additional telemetry that the support desk initiates during a session.

The discipline follows the consent principles found in privacy regulation, particularly the GDPR-style framework that requires consent to be specific, informed, and freely given for the data being processed. It also borrows from the consent design patterns collected by the W3C Privacy Interest Group and from the technical guidance on consent recording published as part of the W3C Technical Report series.

## Workflow or implementation guidance

Consent is requested before any telemetry is collected. The request describes, in plain language, the data being collected, the purpose of the collection, the duration of the collection, the recipient of the data, the retention period, and the customer's right to withdraw. The request is presented to the customer on the same surface as the support session: in the chat window, in the agent's remote-support tool, or in a voice script that the agent reads verbatim.

The customer's response is recorded as a structured event. The event carries the case identifier, the timestamp in UTC, the channel, the agent identifier, the customer identifier (or a session-scoped pseudonym if the customer is not yet identified), the consent scope (the named data classes covered by the request), and the response (granted, denied, partial). A partial response is one in which the customer grants consent for some data classes and denies for others; the consent event records the partial grant explicitly so the collection can proceed only on the granted subset.

If the customer withdraws consent during the session, the withdrawal is recorded as a second structured event. The withdrawal event stops any active collection immediately and triggers a purge of the data already collected, where the data has not yet been integrated into a downstream system. Where the data has already been integrated (for example, into an incident record), the purge is propagated to the downstream system according to its own deletion workflow.

The consent event is stored with the case for the duration of the case plus the audit window required by the records-of-processing policy. The event is exportable to the data subject on request, because the customer has the right to know what they agreed to and when. The export is redacted of identifying information about other parties (the agent, the supervisor) before it leaves the organisation.

## Controls

Controls are layered. At the agent console, the telemetry initiation tool refuses to start a collection without a recorded consent event. The tool surfaces a consent dialog, captures the response, and writes the event before opening the collection channel. At the storage layer, the telemetry stream is keyed to the consent event; if the consent event is later withdrawn, the telemetry stream is purged at the storage layer rather than at the agent layer. At the audit layer, a periodic review confirms that every telemetry collection in the audit window has a matching consent event and that no collection exceeds the granted scope.

A separate control protects against scope drift. The telemetry tool's collection profiles are versioned; the consent event records the profile version, and the storage layer enforces that the collected data classes match the granted profile. If a new profile version adds a data class, the consent must be re-requested before the new class can be collected.

## Validation evidence

Validation is exercised through three routines. First, a synthetic customer journey confirms that the consent dialog appears before any collection begins and that the refusal path is honoured. Second, a sampling review of recent cases confirms that every telemetry collection is paired with a matching consent event. Third, a tabletop exercise simulates a withdrawal-of-consent request and confirms that the data is purged within the service-level objective.

## Failure modes and correction

The most common failure is the silent collection of data before consent is recorded. The correction is the agent-console enforcement that blocks the collection tool until the consent event is written. A second common failure is the collection of data outside the granted scope; the correction is the profile-version matching enforced at the storage layer.

A third common failure is the loss of the consent event. If the event is not stored with the case, the organisation cannot prove that the collection was authorised. The correction is the storage-layer pairing between the consent event and the telemetry stream, and the periodic audit.

## Limitations

The consent discipline assumes that the customer has the legal capacity to consent. Where the customer is acting on behalf of a third party (for example, an employee acting on behalf of an employer, or a guardian acting on behalf of a minor), the consent regime is more complex and may require additional verification. The discipline also assumes that the support desk can identify the data subject. Where the support session is anonymous, the consent event still records the response but the exportability of the event is constrained by the limits of the identifying information.

## Canonical sources

- W3C, Privacy Interest Group, Consent and User Interface Guidance (publisher and title only; canonical W3C landing https://www.w3.org/mission/privacy/).
- W3C, Technical Report publication conventions, https://www.w3.org/TR/
- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management