# oauth-token-binding

**Issue:** Bearer tokens stolen from memory, logs, or network can be replayed by attackers without binding to the original client
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
OAuth access tokens are bearer tokens — whoever has the token can use it. If an attacker steals a token from browser memory, a log file, or a network capture, they can replay it until it expires. Token binding and DPoP (Demonstrating Proof-of-Possession) tie tokens to a specific cryptographic key.

## Pattern / Solution
```javascript
// DPoP (RFC 9449) — proof-of-possession for OAuth tokens
// Generate ephemeral key pair
const dpopKey = await crypto.subtle.generateKey(
  { name: 'ECDSA', namedCurve: 'P-256' },
  false, // non-extractable
  ['sign', 'verify']
);

// Create DPoP proof JWT for each request
async function createDpopProof(url, method, accessToken) {
  const header = { typ: 'dpop+jwt', alg: 'ES256', jwk: await exportPublicKey(dpopKey) };
  const payload = {
    jti: crypto.randomUUID(),
    htm: method,
    htu: url,
    iat: Math.floor(Date.now() / 1000),
    // Include ath (access token hash) when token is available
    ...(accessToken ? { ath: await hashToken(accessToken) } : {}),
  };
  return signJwt(header, payload, dpopKey.privateKey);
}

// Include DPoP proof in API calls
fetch(apiUrl, {
  headers: {
    'Authorization': `DPoP ${accessToken}`,
    'DPoP': await createDpopProof(apiUrl, 'GET', accessToken),
  }
});
```

## Gotchas
- DPoP keys must be non-extractable (`extractable: false`) — otherwise the key can be stolen along with the token.
- The `jti` claim must be unique per request — servers should maintain a short-lived jti replay cache.
- DPoP proofs are bound to the HTTP method and URL — a proof for GET /api/users cannot be replayed against POST /api/admin.
- Server clock skew tolerance should be ≤5 minutes for the `iat` check.

## Related
- `oauth-pkce-flow.md`
- `jwt-best-practices.md`
- `oauth-21-2026.md`
