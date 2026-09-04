# NIST FAL2 Federation Must Be RP-Initiated and Injection-Protected

**Issue:** A federation deployment is treated as NIST FAL2 even though the IdP can push unsolicited federation responses into the RP or the RP has no strong assertion-injection protections.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

NIST SP 800-63C-4 changed the federation-assurance model from the older Revision 3 encryption-centric description. In the final Revision 4 model, FAL2 requires the assertion to be strongly protected from assertion-injection attacks and requires the federation transaction to begin at the RP. These are NIST FAL2 requirements for deployments using that assurance framework, not universal protocol requirements for every federated system.

## Engineering rule

- Start an FAL2 federation transaction from the RP so the RP has transaction state before accepting the response.
- Reject assertions or assertion references that arrive outside the correct stage of an expected federation transaction.
- Bind the response to the initiating transaction using the mechanisms required by the selected federation protocol and NIST profile.
- Use XSS, CSRF, and other relevant injection protections where the presentation mechanism exposes a browser or equivalent intermediary.
- Review old FAL2 documentation that still describes assertion encryption as the defining Revision 4 requirement.

## Verification

- Attempt to submit a valid captured assertion outside a transaction initiated by the RP and confirm it is rejected.
- Attempt to replay or inject a federation response into the wrong transaction and confirm no authenticated RP session is created.
- Trace the RP's transaction state from request through assertion validation and session creation.
- Verify internal documentation cites SP 800-63C-4 rather than superseded Revision 3 requirements.

## Official source

- NIST SP 800-63C-4, Federation Assurance Level 2 and Assertion Injection Protection: https://pages.nist.gov/800-63-4/sp800-63c.html
