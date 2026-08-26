# Keep RATS Evidence Appraisal and Authorization Separate

**Issue:** Remote-attestation evidence, endorsements, reference values, and appraisal results have different issuers and freshness. A successful appraisal is not automatically an authorization decision.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Identify Attester, Verifier, Relying Party, trust anchors, endorsement authorities, and reference-value owners.
- Bind Evidence to a nonce or session and validate freshness and intended use.
- Version appraisal policy and retain the input claims, endorsements, reference values, and result.
- Translate Attestation Results into local authorization through a separate, least-privilege policy.
- Minimize device-identifying claims and define retention.

## Verification
- Replay evidence, substitute endorsements, roll back reference values, and change verifier policy.
- Test unknown claim, stale evidence, compromised verifier, and unavailable endorsement service.
- Trace a relying-party decision to a signed appraisal result and local rule.

## Gotchas
Evidence is not self-verifying, and endorsements are not live measurements. Trustworthiness is time- and policy-dependent.

## Official sources
- [RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.html)
