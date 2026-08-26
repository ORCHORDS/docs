# OAuth JWT access-token profile RFC 9068

**Issue:** A resource server accepts any valid JWT from a trusted issuer as an OAuth access token, allowing an ID token, token for another audience, or ambiguously authorized token to cross protocol and resource boundaries.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Profile boundary

RFC 9068 defines an interoperable JWT profile for OAuth 2.0 access tokens. A conforming token is signed, does not use `none`, identifies itself with the `at+jwt` media type in `typ`, and carries the profile's required claims. The authorization server must not issue a token whose authorization is ambiguous.

## Issuer controls

- Pin allowed signing algorithms and keys per issuer; do not select an algorithm solely from an untrusted header.
- Emit `typ: at+jwt` and keep access-token and OpenID Connect ID-token validation paths separate.
- Set an unambiguous `aud` resource indicator and a subject appropriate to the grant.
- Populate required `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, and `jti` claims.
- Define scope and authorization-detail mapping so the resource server can derive a single enforceable authorization.
- Publish consistent authorization-server metadata and key material; govern key overlap and retirement.

## Resource-server validation

1. Parse with strict size, depth, and duplicate-member limits.
2. Require `typ` to be `at+jwt` or `application/at+jwt`.
3. Verify the signature with an issuer-pinned allowed algorithm and current trusted key.
4. Match `iss` exactly to the configured authorization server.
5. Require `aud` to contain this resource server's identifier.
6. Validate expiration and applicable time policy using a controlled clock.
7. Validate the authorization claims, subject/client relationship, and any replay policy.
8. Reject on every failure; never fall through to an ID-token or generic-JWT validator.

## Verification

Build a negative-token corpus: `alg:none`, wrong `typ`, missing required claims, wrong issuer, sibling API audience, expired token, unknown key, invalid signature, ID token, ambiguous scopes, and duplicated JSON members. Prove each resource server rejects every token except its exact positive profile.

## Gotchas

A valid signature proves only that a trusted key signed the bytes. It does not establish token type, intended resource, authorization, freshness, or replay safety. Encryption, when used, does not replace signature and claims validation.

## Official sources

- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html)
- [RFC 9700: OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
