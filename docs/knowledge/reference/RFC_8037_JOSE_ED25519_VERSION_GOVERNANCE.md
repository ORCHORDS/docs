# RFC 8037 JOSE Ed25519 Version Governance

## Purpose

RFC 8037, *CFRG Algorithms and Algorithms for JOSE* (January 2017), registers the CFRG curves and signatures for JSON Object Signing and Encryption (JOSE): X25519 and X448 for ECDH-ES key agreement, and Ed25519/Ed448 for signatures, with the OKP key type.

Implementations using JOSE with the CFRG algorithms should cite RFC 8037 explicitly, use the registered identifiers and key parameter names, and construct OKP JWKs per the registration.

## Current context and source status

RFC 8037 was published January 2017 as a Standards Track RFC and is not obsoleted. It extends RFC 7518's algorithm registry. The COSE counterpart registrations live in RFC 9053 (verified: Ed25519 value 6 in Table 18, EdDSA -8 in Table 2, OKP key type). JOSE libraries widely implement `OKP` keys with `crv` values `Ed25519`, `X25519`, `Ed448`, `X448`.

## Governance pattern

1. Cite RFC 8037 and use its registered identifiers exactly: algorithm `EdDSA` for Ed25519/Ed448 signatures, `ECDH-ES` with `X25519`/`X448` curves for key agreement, and the `OKP` key type with the `crv` and `x` parameters.
2. Construct OKP JWKs per the registration: `kty: "OKP"`, `crv` naming the curve, `x` as the public key in base64url; private keys carry `d`; no invented parameters.
3. Match curve to use: Ed25519/Ed448 keys sign (EdDSA only); X25519/X448 keys perform key agreement (ECDH-ES only); a key of one class used for the other operation is non-conformant — COSE's registration states the restriction explicitly and JOSE practice follows it.
4. Use `EdDSA` (pure Ed25519) for JWS; RFC 8037 registers EdDSA without prehash variants, and JOSE contexts do not carry Ed25519ph options.
5. For ECDH-ES with X25519, apply RFC 7518's key agreement mechanics; the shared secret feeds theConcat KDF per JOSE, not HPKE.
6. Validate incoming JWKs strictly: `crv` must be one of the registered values, `x` the correct length for the curve (32 bytes for Ed25519/X25519, 57 for Ed448/X448 after base64url decoding).
7. Reproduce RFC 8037's examples (Appendix A) before production use.

## Validation and evidence

Evidence includes:

- identifier usage records matching the RFC 8037 registry;
- JWK construction/strict validation records;
- operation-class separation (sign vs agree) enforced;
- library conformance test outputs;
- RFC 8037 Appendix A examples reproduced.

## Failure correction

Common defects include:

- X25519 keys presented for EdDSA signing or Ed25519 keys used for ECDH — both non-conformant and typically library errors.
- Invented JWK parameters or `crv` values outside the registry.
- Ed25519ph semantics assumed inside JOSE where only pure EdDSA is registered.
- Missing strict `x` length validation allowing malformed keys.

Corrective actions include key class separation, registry-conformant identifiers, strict validation, and library conformance testing.

## Limitations

RFC 8037 registers algorithms for JOSE; it does not define the algorithms themselves (RFC 7748, RFC 8032 do), nor token semantics (RFC 7519 JWT does). COSE equivalents live in RFC 9053 and later registrations; a JOSE↔COSE translation must map identifiers through each registry, not by name similarity.

## Cross-registry identifier discipline

JOSE and COSE name the same curves with different identifier mechanisms: JOSE uses string names (`crv: "Ed25519"`), COSE uses numeric identifiers (curve 6, algorithm -8). Cross-protocol tokens (a JWT verified in a COSE context) require explicit identifier translation through the registries; assuming stable numbering across ecosystems is an interop defect class of its own.

## Canonical sources

- RFC 8037, *CFRG Algorithms and Algorithms for JOSE* (RFC Editor): https://www.rfc-editor.org/rfc/rfc8037
- RFC 9053, *CBOR Object Signing and Encryption (COSE): Initial Algorithms* (RFC Editor, verified Ed25519/OKP registrations): https://www.rfc-editor.org/rfc/rfc9053
- RFC 8032, *Edwards-Curve Digital Signature Algorithms (EdDSA)* (RFC Editor): https://www.rfc-editor.org/rfc/rfc8032
- RFC 7748, *Elliptic Curves for Security* (RFC Editor): https://www.rfc-editor.org/rfc/rfc7748
- IANA — JOSE algorithm registry: https://www.iana.org/assignments/jose/

Sources were verified on September 2, 2026.
