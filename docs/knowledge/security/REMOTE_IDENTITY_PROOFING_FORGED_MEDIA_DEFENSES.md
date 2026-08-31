# Remote Identity Proofing: Digital Injection and Forged-Media Defenses

## Purpose

NIST SP 800-63A-4 adds explicit requirements for defending remote identity-proofing processes against digital injection and forged media, including deepfake images and video. These attacks differ from ordinary presentation attacks because an attacker can insert manipulated media between the capture point and the component that validates evidence, performs biometric comparison, or displays the session to a proofing agent.

A strong design therefore needs controls around the capture path, media integrity, channel protection, detection performance, human review, and operational evidence. A biometric comparison by itself does not prove that the media reaching the comparison system came from a genuine live sensor.

## Threat model

Remote proofing can be attacked at several points:

- a virtual camera can replace a genuine device camera;
- an emulator or compromised device can feed synthetic media into the application;
- identity-document images can be digitally altered before validation;
- face images or video can be generated or modified using deepfake tools;
- captured media can be replaced or manipulated in transit; and
- an attended video session can present generated or replayed content to a proofing agent.

Treat these as pipeline-integrity problems, not only as biometric matching problems.

## Genuine-sensor confidence

SP 800-63A-4 requires technical controls that increase confidence that digital media is being produced by a genuine sensor during the identity-proofing process.

Depending on the implementation, evidence can include detection of:

- virtual-camera use;
- device emulators;
- jailbroken or otherwise compromised devices;
- capture paths that bypass expected application controls; and
- inconsistent or unauthenticated sensor metadata.

NIST also recommends authenticating capture sensors or using device attestation where appropriate to increase confidence in the device that transmits identity-proofing media.

Do not treat device attestation as proof that the applicant is legitimate. It is one signal about the integrity of the capture environment.

## Media analysis

NIST requires digital media submitted during remote identity proofing to be analyzed for indicators of modification, manipulation, tampering, or forgery.

A reusable control pattern includes:

1. Analyze identity-document images, biometric samples, and session video for manipulation indicators relevant to the capture scenario.
2. Test automated detection algorithms against both genuine media and available attack artifacts.
3. Establish baseline false-positive and false-negative performance under conditions resembling the real operating environment.
4. Document the attack artifacts used for evaluation and the corresponding false-negative rates where required.
5. Re-test when the detection model, capture platform, applicant population, or material attack techniques change.
6. Route uncertain or high-risk results to an appropriate manual-review process rather than treating automated output as infallible.

NIST recommends augmenting algorithmic analysis and automated decisioning with manual review to address detection errors.

## Protected transport

Remote identity-proofing data must be exchanged over authenticated protected channels under SP 800-63A-4.

Channel protection reduces the risk that an attacker can substitute media or proofing data between the applicant endpoint and the CSP's processing systems. It does not eliminate endpoint compromise, so it should be combined with genuine-sensor and media-analysis controls.

## Live capture and document presence

Where optical capture and inspection are used for evidence validation, live capture and document-presence checks help distinguish a physical document presented during the session from a pre-generated or manipulated digital copy.

Presentation-attack detection can make digital injection more difficult but is not sufficient by itself. A forged-media attacker may target the path after the sensor or attempt to defeat both media analysis and liveness controls.

## Passive and active detection

NIST recommends passive mechanisms for detecting forged or manipulated media across capture scenarios and recommends analysis for signatures associated with known generative-AI or deepfake tools.

Controls should avoid depending on a single detector. Detection capability can decay as generation methods change, so performance evidence needs periodic refresh.

## Remote attended sessions

For attended remote identity proofing, SP 800-63A-4 adds human-process requirements.

Proofing agents and trusted referees must be trained to identify signs of manipulated media, which can include:

- unusual latency;
- audio/video synchronization problems;
- inconsistent skin tone or resolution;
- implausible transitions or facial movement; and
- other artifacts relevant to the technologies in use.

NIST also requires random human-in-the-loop cues in remote attended collection scenarios. Examples include asking the applicant to perform an unpredictable movement or move an object between the capture sensor and their face.

The purpose of random cues is to make pre-generated or scripted media harder to use reliably. The cues should not create unnecessary accessibility barriers; alternative procedures may be needed for applicants who cannot perform a particular requested action.

## Detection-performance governance

Security claims about forged-media detection should be tied to measured conditions.

Record, where relevant:

- detector/model version;
- media and attack-artifact test sets;
- environmental conditions;
- false-positive and false-negative results;
- known blind spots;
- manual-review thresholds;
- applicant populations included in testing; and
- the date of the last material evaluation.

Avoid statements such as "detects deepfakes" without scope, performance evidence, and limitations.

## Failure and redress handling

Forged-media controls can produce false positives. A failed automated check should therefore connect to documented exception and redress processes rather than silently excluding legitimate applicants.

A useful workflow is:

1. preserve the minimum evidence needed to understand the failed control;
2. avoid exposing sensitive detector internals unnecessarily;
3. route eligible applicants to a manual, attended, or exception-handling path;
4. record the final disposition and reason; and
5. feed confirmed false positives and confirmed attacks back into detector evaluation.

## Privacy and data minimization

Media collected for identity proofing can be highly sensitive. Detection systems should collect and retain only what is justified for proofing, fraud prevention, security, legal, and audit needs.

Introducing additional media analysis does not remove the need for privacy-risk assessment, notice, retention controls, access restrictions, and deletion practices appropriate to the service.

## Operational review checklist

Before deploying or materially changing remote identity proofing, review:

- capture-device integrity controls;
- virtual-camera/emulator detection;
- protected-channel configuration;
- live document capture and presence checks;
- presentation-attack detection;
- forged-media analysis performance;
- manual-review coverage;
- proofing-agent training;
- random attended-session cues;
- exception and redress paths;
- logging and evidence retention; and
- accessibility impacts of anti-fraud controls.

## Sources

- NIST SP 800-63A-4 — Identity Proofing and Enrollment: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63A-4 — Identity Proofing Requirements, including Digital Injection Prevention and Forged Media Detection: https://pages.nist.gov/800-63-4/sp800-63a/ial-general/
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable defensive and governance considerations from NIST SP 800-63A-4. It does not claim that any detector, biometric system, identity-proofing provider, or ORCHORDS service is resistant to all deepfakes or injection attacks or conforms to NIST requirements.