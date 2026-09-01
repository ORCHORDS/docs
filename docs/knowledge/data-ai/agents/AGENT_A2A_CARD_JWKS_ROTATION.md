# Agent A2A Card JWKS Rotation

A signed A2A agent card lets a client verify that a card genuinely describes the agent at a discovered endpoint before sending it tasks. Verification hinges on the JSON Web Key Set (JWKS) the signer publishes: rotate those keys carelessly and either every verification in the wild fails at once, or, worse, an old key stays trusted after compromise. Rotation done well is a publishing discipline with overlap windows, key retirement rules, and cache-aware timing. This article covers the rotation lifecycle for card-signing keys and the client-side behaviors verifiers need during transitions.

## Scope

Applies to operators who sign agent cards in an A2A deployment, and to clients that verify card signatures and cache both cards and JWKS documents. Covers asymmetric signing keys published as JWK sets for card verification, rotation scheduling, dual-publishing windows, and emergency revocation. Does not cover the cryptographic choice of algorithm for card signatures, transport security, or the OAuth credentials an agent uses at runtime, which follow separate key lifecycles.

## Workflow or implementation guidance

1. Separate signing keys from runtime keys. Card signing should use a dedicated key pair (or KMS-held key) whose only purpose is card integrity, so that rotation cadence and compromise response are decoupled from everything else.
2. Set a rotation cadence from the start: a planned rotation interval (commonly between 90 and 365 days), a key age ceiling, and a maximum number of active signing keys (usually one active signer plus recently retired verifiers).
3. To rotate, first publish the new key into the JWKS alongside the old one, but keep signing with the old key. The published set is the overlap window; a verifier fetching the set at any instant can validate signatures made under both keys.
4. After the overlap window exceeds the longest realistic verification-path delay, including JWKS caching and card caching, switch signing to the new key. New signatures use the new `kid`; previously issued cards remain verifiable because the old public key is still published.
5. Retire the old key from the JWKS only when no unexpired signed card still references its `kid`, and after an additional grace period for stale caches. Record the retirement in a key history log with dates, key identifiers, and thumbprints.
6. Serve the JWKS from a stable, well-known HTTPS location derived from the agent's identity, with correct content type, no redirects to different origins, and short but sane cache headers during transitions. Consider sending cache-control hints that force revalidation during a rotation window.
7. For emergency rotation after suspected compromise: publish the replacement key immediately, remove the compromised key from the set as fast as caches permit, shorten the card's validity window so clients re-fetch and re-verify sooner, and publish an out-of-band advisory. Expect some verification failures during the transition and accept them; fail-closed is correct here.
8. As a client, verify by fetching the JWKS fresh when a signature's `kid` is unknown, respecting cache headers but bounding how long an unknown-`kid` state can persist before hard failure. Never fetch keys from a URL embedded solely in the card or signature; derive key locations from trusted configuration or well-known paths tied to the agent's origin.

## Controls

- Key inventory: every signing key has an owner, creation date, activation date, planned retirement, and thumbprint, all in an append-only log.
- Overlap-window enforcement: tooling refuses to retire a key while unexpired cards reference it, and refuses to sign with a key not yet present in the published set.
- Monitoring: JWKS fetch success rate, verification outcome by `kid`, and the fraction of verifications served from cached keys, watched before, during, and after each rotation.
- Client-side pinning policy optional per deployment: high-security verifiers may pin key thumbprints and treat rotation as a manual re-approval event, accepting operational cost for control.
- Rate limiting and size limits on the JWKS endpoint to prevent it being used as a resource-exhaustion vector.

## Validation evidence

- Rotation drill in a staging environment with real cached verifiers: rotate a key, then confirm that a card signed with the old key, a card signed with the new key, and a card signed with a never-published key produce respectively: valid, valid, and rejected, across the entire overlap window.
- Clock-shift tests: verify a client with a skewed clock still resolves correctly using the overlap window rather than rejecting everything.
- Compromise drill: simulate emergency retirement and measure time-to-rejection for cards signed by the removed key across clients with different cache states.
- Evidence pack per rotation: diff of the JWKS before and after, the signing cutover timestamp, the retirement timestamp, verification success-rate graphs spanning the window, and the approver of record.

## Failure modes and correction

- Signing cutover happens before the new key is published, producing a burst of unknown-`kid` failures. Correction: automated preflight that blocks signing with an unpublished key, plus client retry-with-refresh behavior on unknown `kid`.
- The old key is dropped from the JWKS while long-cached cards still reference it, causing permanent verification failure for otherwise valid cards. Correction: retirement gating on card expiry, and client logic that re-fetches the card itself when a `kid` cannot be resolved.
- Multiple publishing paths (CDN plus origin) diverge during rotation, so different verifiers see different key sets. Correction: rotation runbooks include cache-purge checks at every layer, and monitoring compares set digests across vantage points.
- Compromised key stays trusted because emergency removal waits for a scheduled cache TTL. Correction: shorten TTLs near rotation events, and design verifiers to accept out-of-band revocation signals.

## Limitations

Rotation protects against key compromise only after detection; a patient attacker with a stolen key inside the overlap window still signs valid cards until retirement. Verification ultimately anchors in the trustworthiness of the JWKS hosting origin, so DNS or hosting compromise defeats the scheme regardless of cadence. Very long card cache lifetimes work against fast revocation, forcing a trade between client load and response time. Finally, `kid` handling is a convention; deployments that omit `kid` force verifiers into ambiguity that rotation makes worse, so it should be mandatory in local policy even where optional in the protocol.

## Canonical sources

- A2A Protocol Specification (Agent2Agent), latest version: https://a2a-protocol.org/latest/specification/
- RFC 7517, JSON Web Key (JWK): https://www.rfc-editor.org/rfc/rfc7517
- RFC 7515, JSON Web Signature (JWS): https://www.rfc-editor.org/rfc/rfc7515
