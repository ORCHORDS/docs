# saml-replay-attack-prevention

**Issue:** SAML assertions without replay prevention can be captured and resubmitted to authenticate as another user
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SAML assertions have a validity window (typically 5 minutes). If an attacker intercepts a valid assertion (e.g., via network sniffing, XSS, or IdP-initiated SSO abuse) they can resubmit it within that window to authenticate as the victim, even after the legitimate session has ended.

## Pattern / Solution
```python
# python3-saml — built-in replay prevention via assertion cache
settings = {
    "security": {
        "wantAssertionsSigned": True,
        "wantMessagesSigned": True,
        "rejectUnsolicitedResponsesWithInResponseTo": True,
    }
}
# Library maintains a cache of seen assertion IDs and rejects duplicates

# Manual implementation: store assertion IDs with TTL
import redis
r = redis.Redis()

def check_assertion_replay(assertion_id, not_on_or_after):
    key = f"saml:assertion:{assertion_id}"
    if r.exists(key):
        raise SecurityError("SAML assertion replay detected")
    ttl = not_on_or_after - datetime.utcnow()
    r.setex(key, int(ttl.total_seconds()) + 60, "used")
```
```
Additional controls:
- Use SP-initiated SSO exclusively (include AuthnRequest ID in InResponseTo)
- Set short NotOnOrAfter windows (< 5 minutes)
- Enforce HTTPS for all SSO endpoints to prevent interception
- Reject assertions with NotBefore in the future or NotOnOrAfter in the past
```

## Gotchas
- IdP-initiated SSO has no `InResponseTo` — either disable it or implement robust replay detection.
- Assertion caches must survive service restarts — use Redis/database, not in-memory.
- Clock skew between SP and IdP can cause valid assertions to be rejected — allow ≤2 minutes skew.
- Multiple SP instances need a shared assertion cache — per-instance caches allow cross-instance replays.

## Related
- `saml-xml-signature-wrapping.md`
- `saml-sp-workers.md`
