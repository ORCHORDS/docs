# NIST SP 800-63C-4 Federation Assurance Controls

**Issue:** A signed federation assertion can still be replayed, sent to the wrong relying party, over-disclose attributes, or exceed the trust agreement between the identity provider and relying party.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Select and document the Federation Assurance Level from risk analysis, then use a federation protocol and assertion protection that meet that level.
- Validate issuer, audience, signature, time bounds, nonce or transaction binding, and replay controls before creating a relying-party session.
- Bind the assertion to the intended relying party and session; use stronger proof-of-possession or holder-of-key mechanisms where the selected level requires them.
- Maintain an explicit IdP-RP trust agreement covering identifiers, keys, attribute semantics, assurance signals, incident handling, and termination.
- Release only attributes required by the relying party and preserve user notice, consent, privacy, and pairwise-identifier policy where applicable.
- Define logout, session expiry, key rollover, compromise, federation revocation, and recovery behavior; a valid signature alone is not lifecycle management.

## Verification
- Replay a captured assertion, alter audience and issuer, test stale time windows, and rotate signing keys.
- Compare released attributes against the agreement and current purpose for every relying party.
- Simulate IdP compromise or relationship termination and confirm new sessions stop while local sessions follow documented containment policy.

## Gotchas
Identity, authenticator, and federation assurance are separate dimensions. Do not infer IAL or AAL solely from a federation protocol or token format.

## Official sources
- https://csrc.nist.gov/pubs/sp/800/63/c/4/final
- https://pages.nist.gov/800-63-4/
