# Identity-Proofing Injection and Forged-Media Review Template

Use this record to assess remote identity-proofing capture, media-integrity, and fraud-detection controls against NIST SP 800-63A-4. Keep attack artifacts, production telemetry, and device-specific sensitive evidence in protected systems rather than this public record.

## Review metadata

- Identity service: `<name>`
- Proofing type: `<remote unattended/remote attended/hybrid>`
- Reviewer: `<role or team>`
- Review date: `<YYYY-MM-DD>`
- Optical/biometric/video capture components: `<summary>`

## Capture-source controls

| Control area | Implementation | Test evidence | Result |
| --- | --- | --- | --- |
| Genuine-sensor confidence | `<device attestation/virtual-camera detection/etc.>` | `<reference>` | `<pass/fail>` |
| Emulator/jailbreak detection | `<implementation>` | `<reference>` | `<pass/fail>` |
| Protected channel | `<implementation>` | `<reference>` | `<pass/fail>` |
| Media modification/forgery analysis | `<implementation>` | `<reference>` | `<pass/fail>` |
| Manual review/escalation | `<implementation>` | `<reference>` | `<pass/fail>` |

## Detection-performance evidence

- Genuine-media dataset used: `<reference>`
- Attack-artifact categories tested: `<categories>`
- False-positive measurement: `<result>`
- False-negative measurement: `<result>`
- Performance documentation owner: `<role>`

## Remote attended checks

- [ ] Proofing agents are trained to identify manipulation, coercion, social engineering, and media anomalies.
- [ ] Randomized human-in-the-loop cues are used where required by the selected NIST proofing scenario.
- [ ] Proofing agents can safely flag suspected fraud.
- [ ] Fraud flags produce durable investigation evidence without exposing sensitive internals to the applicant.

## Verification scenarios

| Scenario | Expected | Actual | Evidence |
| --- | --- | --- | --- |
| Virtual camera or emulated source | `<detect/block/escalate>` | `<result>` | `<reference>` |
| Manipulated image/video | `<detect/block/escalate>` | `<result>` | `<reference>` |
| Genuine capture | `<accept>` | `<result>` | `<reference>` |
| Suspicious attended interaction | `<flag/escalate>` | `<result>` | `<reference>` |

## Findings and actions

- Findings: `<text>`
- Corrective actions/owner/date: `<text>`
- Retest result: `<result>`

## Sources

- NIST SP 800-63A-4, Digital Injection Prevention and Forged Media Detection: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63A-4, Identity Assurance Level Requirements: https://pages.nist.gov/800-63-4/sp800-63a/ial/
