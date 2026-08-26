# OpenID Front-Channel Logout and Browser Partitioning

**Issue:** OpenID Connect front-channel logout depends on a browser loading relying-party iframes. Third-party cookie blocking, storage partitioning, or network failure can leave an RP session active even after the provider reports logout.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Register an exact HTTPS `frontchannel_logout_uri` and do not accept arbitrary logout destinations from request parameters.
- When `iss` and `sid` are supplied, validate them as the issuer-session pair for the local RP session before clearing it.
- Return a small response with `Cache-Control: no-store` and avoid redirects, user interaction, or dependencies that can block iframe completion.
- Make logout idempotent and clear only the intended issuer session; do not use a bare `sid` across issuers.
- Combine front-channel logout with back-channel logout where supported, short local session lifetime, token revocation or expiry, and risk-based server-side invalidation.
- Treat browser completion as best effort and surface partial-logout telemetry without exposing session identifiers.

## Verification
- Test with third-party cookies blocked, storage partitioned, iframe loading disabled, and one RP offline.
- Replay and mix `iss` and `sid` values and confirm no unrelated session is cleared.
- Verify back-channel or expiry containment terminates a session that missed the front-channel iframe.

## Gotchas
A successful OP logout page does not prove every embedded RP processed the request. Browser privacy controls make front-channel delivery inherently non-durable.

## Official sources
- https://openid.net/specs/openid-connect-frontchannel-1_0.html
- https://openid.net/specs/openid-connect-backchannel-1_0.html
