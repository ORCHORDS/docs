# oauth-pkce-flow

**Issue:** OAuth authorization code flow without PKCE is vulnerable to authorization code interception in public clients
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mobile apps and SPAs (public clients that cannot store a client secret) using the authorization code flow are vulnerable to code interception via malicious apps registered for the same redirect URI scheme. PKCE (Proof Key for Code Exchange) binds the code to the original requester.

## Pattern / Solution
```javascript
// PKCE flow in a SPA
async function startOAuthFlow() {
  // 1. Generate code verifier (random 43-128 char string)
  const codeVerifier = generateRandomString(64);
  sessionStorage.setItem('pkce_verifier', codeVerifier);

  // 2. Derive code challenge (S256 method)
  const encoder = new TextEncoder();
  const data = encoder.encode(codeVerifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  const codeChallenge = btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');

  // 3. Redirect to authorization endpoint with challenge
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    state: generateRandomString(16),
  });
  window.location.href = `${AUTH_ENDPOINT}?${params}`;
}

// 4. Exchange code with verifier (not challenge)
async function exchangeCode(code) {
  const codeVerifier = sessionStorage.getItem('pkce_verifier');
  const response = await fetch(TOKEN_ENDPOINT, {
    method: 'POST',
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      code,
      redirect_uri: REDIRECT_URI,
      client_id: CLIENT_ID,
      code_verifier: codeVerifier,  // proves we started the flow
    }),
  });
}
```

## Gotchas
- `code_challenge_method: plain` provides no security benefit — always use `S256`.
- The code verifier must be stored securely (sessionStorage per tab) and discarded after use.
- PKCE does not replace `state` parameter — still needed for CSRF protection.
- Authorization servers that don't enforce PKCE can be downgraded to plain flow — verify server enforces it.

## Related
- `oauth-token-binding.md`
- `oauth-best-practices.md`
- `oauth-21-2026.md`
