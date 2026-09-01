# FedCM Credential Management API Integration

## Scope

Integrating the Federated Credential Management (FedCM) API on the identity-provider side: declaring the `/.well-known/web-identity` endpoint, serving the IdP config and per-client metadata JSON, rendering the accounts list, handling the token endpoint, and sequencing `navigator.credentials.get()` on the relying-party page. Covers the three-party request flow, login status (`Set-Login`), the browser-mediated UI contract, and the errors the API throws when the well-known chain is misconfigured. Excludes passkeys/WebAuthn and the password-credential side of the Credential Management API, and excludes the IdP server-side session architecture.

## Workflow or implementation guidance

FedCM exists to fix third-party cookie deprecation for federated login: the browser itself fetches IdP endpoints (with the IdP's cookies, as same-site requests from the browser) and renders the account chooser in branded chrome, so no cross-site cookie flows through page-embedded scripts. That inversion — the browser as the fetcher — is the reason the configuration is endpoint-shaped rather than script-shaped.

The IdP must serve three documents. First, `https://idp.example/.well-known/web-identity`:

```json
{
  "provider_urls": ["https://idp.example/fedcm/config.json"]
}
```

Second, the provider config at that URL:

```json
{
  "accounts_endpoint": "/fedcm/accounts",
  "client_metadata_endpoint": "/fedcm/client_metadata",
  "id_token_endpoint": "/fedcm/idtoken",
  "login_url": "https://idp.example/login"
}
```

Third, the accounts endpoint returns the accounts the currently-logged-in IdP user is willing to surface, each with `id`, `name`, `email`, `given_name`, and `picture`:

```json
{
  "accounts": [
    { "id": "u_1234", "given_name": "Dana", "name": "Dana Okoro",
      "email": "dana@idp.example", "picture": "https://idp.example/u/1234.png" }
  ]
}
```

The relying party then requests a federated credential:

```js
const credential = await navigator.credentials.get({
  identity: {
    providers: [{ clientId: 'rp-client-id', configURL: 'https://idp.example/fedcm/config.json' }],
    mode: 'active'  // or 'passive' for silent mediation in an autofill flow
  },
});
// credential.token is the value the id_token_endpoint returned
```

The browser resolves `configURL` against the well-known file (the provider URL must be listed there or the whole call rejects), fetches accounts with the user's IdP session, shows the account sheet, and on user approval POSTs to the `id_token_endpoint` with `client_id`, `account_id`, `disclosure_text_shown`, and a crypto nonce. The IdP mints a token (typically a signed JWT binding the account to that client); the RP's server verifies it and establishes its own first-party session.

Login status gating: the browser tracks `Set-Login: login` / `Set-Login: logged-out` (or the legacy `Set-Login-Status` header) sent by the IdP origin, and `navigator.login.setStatus()` from IdP-origin iframes. When the browser believes the user is logged out, an `active` mode `get()` fails immediately with `NetworkError` and shows a "sign in to continue" prompt instead of the account list — the account fetch is never attempted. Every IdP response should therefore carry the header, especially the logout response after a session ends, or users get stuck in a "logged-in at IdP, logged-out per browser" limbo that only clears after the three-minute error timeout.

`mode: 'passive'` combined with `mediation: 'silent'` (or `'optional'` in autofill contexts) lets the RP discover a returning federated user with zero UI: if exactly one account and one provider resolve, the token returns directly; any ambiguity resolves to `IdentityCredentialError` or a null credential and the RP falls back to an `active` prompt. The auto-reauthn prompt (`identity.providers` plus `context: 'continue'`) is the middle tier for returning users.

## Controls

- Serve `.well-known/web-identity` and the config JSON with `Content-Type: application/json` and permissive `Access-Control-Allow-Origin` handling as the spec requires — the browser fetch is credentialed, so the endpoints must not redirect across origins.
- Send `Set-Login: login|logged-out` on every IdP navigation response; mirror session destroy with the logged-out value.
- Keep `client_metadata_endpoint` returning `privacy_policy_url` and `terms_of_service_url` per client ID so the disclosure sheet renders.
- Gate the RP's token acceptance on server-side verification of the IdP signature and audience (`client_id`) — the token is untrusted input.
- Wrap every `credentials.get({ identity })` call in feature detection (`'IdentityProvider' in window` or a try/catch on `TypeError`) and treat failure as "fall back to redirect-based OAuth".

## Validation evidence

- Full-matrix integration test: fresh browser profile → `get()` in active mode → account sheet shows; select account → token endpoint receives POST with expected `account_id` → RP session cookie set.
- Logged-out-path test: destroy the IdP session, confirm the response carried `Set-Login: logged-out`, then call `get()` and assert the documented `NetworkError`/login-prompt path rather than a stale account list.
- Well-known chain check in CI: `curl -s https://idp.example/.well-known/web-identity | jq '.provider_urls[]'` and assert it lists the exact configURL the RP ships; a mismatch is the single most common silent breakage.
- DevTools verification: the Network panel shows browser-initiated `accounts` and `id_token` requests attributed to `fedcm:` initiator, proving the page never fetched them itself.

## Failure modes and correction

- `The request failed because the IdP config could not be fetched` (`NetworkError`): configURL not listed in the well-known `provider_urls`, a redirect on the config fetch, or wrong content type. Fix the chain, not the RP code.
- Account picker never appears and the call rejects immediately: browser login status says logged-out. Audit every IdP response for the missing `Set-Login` header, especially 204 logout responses.
- Token endpoint receives no `Cookie` header: the IdP session cookie lacks `SameSite=None; Secure`, so the browser's credentialed fetch arrives anonymous and the accounts list comes back empty.
- `IdentityCredentialError` with the IdP's own error URL payload: the IdP rejected the request (unknown client, disabled account); surface the IdP-provided code, and never retry in a loop — the API enforces a cooldown after repeated failures.
- Pictures broken in the chooser: `picture` URLs must be CORS-fetchable and absolute; relative paths resolve against the config origin and fail silently in some implementations.
- RP calls `get()` on page load in active mode without a user gesture: the prompt is suppressed; anchor it to a sign-in button click.

## Limitations

- Chromium-first shipping surface; other engines' coverage is partial or absent depending on version — the redirect-based OAuth flow must remain the fallback path.
- The browser UI (account sheet, disclosure text) is not stylable; brand accommodation is limited to logos and the per-client metadata strings.
- Button-mode and continuation flows vary across Chromium versions; pin behavior per verified version rather than assuming a uniform surface.
- Only a fixed set of endpoints is browser-fetched; anything beyond accounts/metadata/token (profile enrichment, multi-step consent) requires the IdP's own pages outside FedCM.
- Chrome may enforce metrics/attestation reporting endpoints in certain configurations; omitting them can limit flow visibility without failing the login.

## Canonical sources

- W3C FedID CG, Federated Credential Management API: https://fedidcg.github.io/FedCM/
- MDN, FedCM API overview: https://developer.mozilla.org/en-US/docs/Web/API/FedCM_API
- MDN, `IdentityProvider` interface: https://developer.mozilla.org/en-US/docs/Web/API/IdentityProvider
