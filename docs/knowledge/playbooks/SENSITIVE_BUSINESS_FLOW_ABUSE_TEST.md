# Sensitive Business Flow Abuse Test

## Trigger
Run before launch or material change of a flow where automation, repetition, speed, scarcity, incentives, or limited capacity can create business harm.

## Inputs
- Flow description and business owner.
- Definition of harmful automated behavior.
- Legitimate high-volume use cases.
- Existing quotas, velocity controls, verification steps, and telemetry.

## Procedure
1. Ask the business owner to define what makes automated use harmful in measurable terms.
2. Identify the resources or outcomes an attacker would try to exhaust, monopolize, inflate, or manipulate.
3. Map the controls intended to constrain that abuse, such as quotas, velocity limits, reservation rules, behavioral checks, or human verification.
4. Automate the flow at increasing speed and volume while preserving otherwise valid requests.
5. Test distributed behavior across accounts or client identities where the threat model requires it.
6. Confirm legitimate high-volume paths remain supported through explicit policy rather than informal bypasses.
7. Measure false positives, rejected abuse attempts, and any control gaps.
8. Adjust thresholds only with business-owner approval and repeat the exercise.

## Escalation
Escalate when harmful automated behavior succeeds within the documented abuse model or when the business owner cannot define an acceptable automation boundary for a sensitive flow.

## Evidence
- Abuse model and thresholds.
- Test scenarios and traffic profile.
- Control decisions and results.
- Exceptions, owners, and retest evidence.

## Completion criteria
The flow has a documented automation-abuse policy and demonstrated controls that constrain the modeled abuse while preserving approved legitimate use.

## Source basis
- OWASP API6:2023 Unrestricted Access to Sensitive Business Flows: https://owasp.org/API-Security/editions/2023/en/0xa6-unrestricted-access-to-sensitive-business-flows/
