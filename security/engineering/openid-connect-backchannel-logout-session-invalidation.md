# OpenID Connect back-channel logout: session invalidation and replay safety

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)

## Problem

Browser-mediated logout cannot reliably clear a relying party session when its tab is inactive. Back-channel logout provides direct OP-to-RP invalidation, but the receiver must treat the logout token as a security event rather than a browser callback.

## Practice

- Register a dedicated HTTPS back-channel logout URI and ensure the identity provider can reach it.
- Validate the Logout Token signature, issuer, audience, issued and expiry times, event claim, and the absence of nonce before changing session state.
- Require a session ID when your policy needs session-specific logout; otherwise define how subject-wide logout affects all sessions for that issuer and subject.
- Store recent logout-token IDs for a bounded period to make delivery idempotent and detect replay.
- Invalidate server-side sessions and refresh-token associations; do not rely solely on clearing browser cookies.
- Return safe, stable failures and alert on validation or reachability problems without logging the raw logout token.

## Verification

1. Log out one known session and confirm that only the intended session is invalidated when a session ID is present.
2. Deliver the same valid logout token twice; the result must be idempotent.
3. Send tokens with invalid signature, issuer, audience, expiry, event, nonce, or token ID replay; all must be rejected.
4. Simulate unreachable RP delivery and verify the provider retry and operational response match policy.

## Failure modes

- A generic JWT endpoint accepts an ID token or another token type as a logout request.
- Clearing a browser cookie leaves server-side sessions or refresh capability active.
- Subject-wide invalidation accidentally logs out unrelated issuer or tenant sessions.

## Related

- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html)
