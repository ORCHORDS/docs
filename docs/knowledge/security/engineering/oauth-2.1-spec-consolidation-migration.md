# oauth-2.1-spec-consolidation-migration

**Issue:** OAuth deployments built on the original RFC 6749 (2012) still permit flows and behaviors that the working group has spent a decade identifying as dangerous — optional PKCE, prefix-matched redirect URIs, the implicit grant, the password grant, and bearer tokens passed in query strings. OAuth 2.1 (draft-ietf-oauth-v2-1) consolidates the security fixes from RFC 7636, RFC 8252, and the Bearer Token RFC into one baseline, and authorization servers are progressively enforcing it. Teams that audit their clients and servers against 2.1 now avoid forced, rushed migrations when their provider flips enforcement on.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What OAuth 2.1 changes

1. **PKCE becomes mandatory for every authorization-code client.** RFC 7636 made PKCE optional and primarily aimed at public clients; 2.1 requires `code_challenge`/`code_verifier` for all clients using the code flow, confidential ones included, closing the authorization-code interception class of attacks.
2. **Redirect URIs must match exactly, byte for byte.** Prefix and wildcard matching are gone. A registered `https://app.example.com/callback` will not match `https://app.example.com/callback/` or `https://app.example.com/callback/x`, which kills open-redirect-via-redirect-uri techniques.
3. **The implicit grant (`response_type=token`) is removed.** Tokens exposed in front-channel URL fragments leak through browser history, referrers, and extensions; every implicit use case is served better by code + PKCE.
4. **The Resource Owner Password Credentials grant is removed.** ROPC trains users to type passwords into third-party clients, makes phishing indistinguishable from legitimate prompts, and blocks any evolution toward MFA or passkeys.
5. **Bearer tokens must not appear in request URLs.** Query strings are logged by proxies, servers, and analytics; 2.1 forbids the `access_token` query parameter defined by RFC 6750 — tokens travel in `Authorization` headers or message bodies.
6. **Nothing genuinely new is added.** 2.1 is a consolidation: the correct reading of any "new" requirement is "this was already a best practice in a later RFC; now it is the floor."

## Migration checklist for relying parties and clients

1. **Inventory every OAuth client you operate.** List each client's grant types, `redirect_uri` registrations, and whether it sends PKCE today; anything using implicit or ROPC is a migration item, not a nice-to-have.
2. **Convert implicit clients to authorization code + PKCE.** SPAs move to code flow with PKCE and no client secret; native apps follow RFC 8252 using the system browser and an https or private-scheme loopback redirect.
3. **Delete ROPC integrations.** Replace password grant with authorization code (user present) or client credentials (machine-to-machine); if a legacy vendor only supports ROPC, treat that vendor as a liability with an exit plan.
4. **Normalize registered redirect URIs.** Trim trailing slashes, drop query-string parameters from registrations where the server disallows them, and register one exact URI per distinct callback rather than one prefix.
5. **Add `code_verifier` generation and `S256` challenge hashing.** Use a high-entropy verifier (43–128 chars from a CSPRNG) and always `code_challenge_method=S256` — `plain` exists only for environments that cannot hash and should not appear in new code.
6. **Purge access tokens from URLs.** Search codebases and logs for `access_token=` in outbound requests and for tokens captured from fragments; move all programmatic use to the `Authorization: Bearer` header.

## Authorization-server enforcement steps

1. **Reject non-exact redirect URI matches with an error, not a redirect.** Responding to a mismatch with a redirect to the registered value teaches nothing and can be abused; fail the request visibly so client owners notice during their own testing.
2. **Refuse authorization-code requests without PKCE parameters.** If a staged rollout is needed, start by logging non-PKCE requests per client, then warn, then hard-fail on a published date.
3. **Disable implicit and ROPC per client, then globally.** Annotate tokens issued via legacy grants so you can measure remaining traffic and chase the last consumers before removal.
4. **Issue sender-constrained or at minimum short-lived tokens.** Pair the 2.1 floor with DPoP or mTLS binding and token lifetimes in minutes, so a stolen bearer token is worth far less.
5. **Log grant type, PKCE presence, and redirect match outcome per authorization event.** These three fields turn "why did this break" postmortems into a one-line query.

## Verification

1. **Fuzz the redirect handler.** Submit the registered URI with appended paths, extra slashes, case changes, and appended query parameters; every variant must be refused with no redirect issued.
2. **Attempt a code flow without `code_challenge`.** The server must reject it; intercepting the code in a test and replaying it with a wrong or missing verifier must also fail.
3. **Grep production request logs for tokens in query strings.** Any hit is either a legacy client or a leak; both need remediation before 2.1 enforcement is safe to enable.
4. **Confirm no client can obtain a token via `response_type=token` or `grant_type=password`.** Both endpoints should return unsupported-grant-type errors.

**Source:** [oauth.net OAuth 2.1](https://oauth.net/2.1/), [draft-ietf-oauth-v2-1](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-10), [FusionAuth OAuth 2.0 vs 2.1](https://fusionauth.io/articles/oauth/differences-between-oauth-2-oauth-2-1), [WorkOS OAuth 2.1 vs 2.0](https://workos.com/blog/oauth-2-1-vs-oauth-2-0).
