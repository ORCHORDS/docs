# Remote Identity Proofing Needs Injection and Forged-Media Defenses

**Issue:** A remote identity-proofing system relies on ordinary image/video capture and proofing-agent judgment without controls for virtual cameras, emulators, injected media, or deepfake content.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63A-4 adds explicit digital-injection and forged-media defenses for remote identity proofing. For remote proofing processes that use optical capture or recognition, NIST requires technical controls that increase confidence media came from a genuine sensor and requires analysis for signs of modification, manipulation, tampering, or forgery. Remote attended proofing also adds trained-agent and randomized human-in-the-loop cues.

## Engineering rule

- Treat the media-capture path as part of the trust boundary, not just the comparison algorithm.
- Detect or constrain virtual cameras, device emulators, jailbroken devices, and other paths that reduce confidence in the capture source.
- Analyze submitted media for manipulation/forgery indicators and maintain evidence about the detector's measured false-positive and false-negative behavior.
- Protect remote proofing exchanges with authenticated protected channels.
- For remote attended sessions, combine trained human review with randomized interaction cues rather than assuming a live agent alone defeats forged media.
- Frame these as NIST identity-proofing requirements for services using that assurance framework, not as a universal legal mandate for every application.

## Verification

- Exercise the proofing flow with safe test fixtures representing a virtual camera, emulated capture source, and manipulated media.
- Confirm disallowed or suspicious media is detected, contained, or escalated according to policy before identity proofing succeeds.
- Verify proofing agents can flag suspected fraud and that the resulting event is preserved for investigation.
- Measure and retain detector performance against genuine and attack-artifact datasets used by the organization.

## Official sources

- NIST SP 800-63A-4, Digital Injection Prevention and Forged Media Detection: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63A-4, Identity Assurance Level Requirements: https://pages.nist.gov/800-63-4/sp800-63a/ial/
