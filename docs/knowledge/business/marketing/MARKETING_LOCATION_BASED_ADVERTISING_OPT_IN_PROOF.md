# Location-Based Advertising Opt-In Proof

## Scope

This control governs the capture, storage, and production of opt-in evidence for marketing that uses location data, including precise device location (GPS, fine Wi-Fi triangulation, Bluetooth beacons), coarse location (cell tower, IP-derived geolocation), inferred location (billing or shipping addresses converted to a region), beacons encountered in a physical space, and reverse-IP country or region. It applies to push notifications triggered by entering or leaving a geofence, in-app offers based on the user's location, retail beacon marketing, store-visit attribution, attribution that moves events from a digital click to a physical visit, advertising audiences built on location segments, and any external transfer or sale of derived location signals.

The governing reference is Article 6 of the General Data Protection Regulation, which sets the conditions under which processing of personal data — including location data that identifies or can identify a natural person — is lawful. Article 6 lists the lawful bases, including consent, performance of a contract, compliance with a legal obligation, protection of vital interests, performance of a task carried out in the public interest, and the controller's legitimate interests. Location data warrants explicit consent in many EU member-state implementations and under the ePrivacy Directive for electronic communications, but this article uses Article 6 as the consent-proof baseline because it names consent as a specific lawful basis.

## Workflow or implementation guidance

The location-based advertising workflow proceeds in six steps.

1. Determine the lawful basis. The privacy and legal team identifies, before any collection, the lawful basis that applies to a given processing: consent for direct marketing to individuals in the EU/UK, contractual necessity for service features the user has signed up for, legitimate interest for fraud prevention where that is the operative interest, or another basis where the regime permits it.
2. Capture consent where consent is the basis. The consent capture is specific, informed, freely given, unambiguous, and withdrawable at any time. It names the controller, the processing purpose, the data category (precise location, coarse location, beacon events), the recipients, and the retention period. A separate consent is required for cross-context behavioral advertising than for service-related location, and a separate consent is required for any transfer to a third party.
3. Store the consent proof. The proof is stored at the user level or, where the data subject cannot be uniquely identified, at the device or household level. The proof records what was shown, what the user agreed to, when, on which surface, in which language, and via which consent mechanism (in-app modal, web banner, OS-level prompt, contractual clause).
4. Sync to advertising systems. The advertising audience, the geofence trigger, the retargeting segment, and any external recipient receive the consent signal before the user is added. A lack of consent signal triggers a deny-by-default state in the destination system.
5. Run the campaign with logs. Each audience member added or removed from a location-triggered campaign is logged, with the consent reference, the trigger event, and the destination system identifier. Logs are retained at least for the active consent period and for the audit window after.
6. Withdraw on demand. A withdrawal request via any reasonable channel (in-app toggle, web form, email, support ticket, postal request) is honored promptly. Withdrawal is propagated to every recipient system, and downstream processing stops. The control does not erase system logs of past processing without a separate legal basis.

## Controls

The controls in this workflow ensure that a defensible consent or other lawful basis exists at the moment location data is used for marketing.

- Every audience that uses location data has a named lawful basis and a record of that basis (consent artifact, contractual reference, or legitimate-interest assessment).
- Consent capture is granular: consent for service delivery is captured separately from consent for marketing, and consent for cross-context behavioral advertising is captured separately from consent for first-party analytics.
- Consent is withdrawable at any time through the same surface that captured it and through reasonably accessible alternatives.
- The audience system is deny-by-default: identifiers without a current consent signal are excluded from location-triggered sends.
- The retention period is documented. Periods longer than the documented retention require a new basis or evidence of overriding legal obligation.
- Any third-party recipient is identified in the consent text, and the addition of a new recipient after consent was collected is treated as a new consent event.
- Geographic precision is the lowest the use case requires: precise GPS is requested only when coarse geolocation cannot deliver the campaign outcome.

## Validation evidence

Evidence is collected for the consent record itself and for the campaign that relies on it.

- Consent record: surface, version of the consent text shown, language, timestamp, IP and user agent where available, the lawful basis, and the recipient list.
- Withdrawal record: timestamp, channel, propagation timestamps to all downstream systems, and confirmation that the user no longer appears in the active audience.
- Audience membership log: for a sample of campaign recipients, the consent identifier, the location trigger, and the recipient system identifier.
- Lawful-basis schedule: a list of every location-based audience with the lawful basis applied and the review date.
- Audit log of disclosures provided to data-protection authorities where required.

## Failure modes and correction

Frequent failures include collecting precise location under a service-purpose consent and using it for marketing, surfacing consent in a flow that bundles unrelated purposes, treating "legitimate interest" as a default without a documented assessment, using inferred location (for example, billing address) as if it carried the same consent as precise consent, sharing location-derived audiences with downstream parties not named in the consent, and failing to honor withdrawal across recipients. Another failure is implicitly asserting that the user agreed because the platform permission is granted, when the platform permission is not equivalent to GDPR Article 6 consent.

Correction starts by removing the user from any location-based audience whose consent cannot be reproduced. The audience segmentation is reviewed so that all members have an identifiable lawful basis with a surviving record. Future campaigns are blocked from re-introducing the affected audience until the consent state is clarified. The consent capture surface is updated if the failure originated there; if the failure was downstream, the recipient system is updated and tested for honor of withdraw. The root cause entry identifies whether the failure was a data defect, a consent surface defect, a propagation defect, or a lawful-basis misclassification, and updates the relevant control.

## Limitations

This control does not determine whether a particular data flow is "personal data" or whether a particular inference is "data concerning health" or other special category under the GDPR; classification requires legal review. It does not adjudicate the application of the ePrivacy Directive, national implementations of cookies and similar technologies, or sector-specific regimes (telecommunications, financial services, children's data). It does not replace data-protection impact assessments, records of processing activities, or data-subject rights workflows (access, rectification, erasure, portability, restriction, objection). It is an operational control, not a legal determination.

## Canonical sources

- **Primary authority 1 — Regulation (EU) 2016/679, General Data Protection Regulation, Article 6 (Lawful processing):** [https://gdpr-info.eu/art-6-gdpr/](https://gdpr-info.eu/art-6-gdpr/)
- **Primary authority 2 — EUR-Lex, consolidated text of GDPR Article 6:** [https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32016R0679)
