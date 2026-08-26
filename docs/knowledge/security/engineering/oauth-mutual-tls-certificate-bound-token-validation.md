# OAuth mutual-TLS certificate-bound token validation

**Issue:** A service may authenticate a client with mutual TLS at token issuance yet accidentally accept the issued access token as a bearer token at the API. That leaves a stolen token reusable by another client. RFC 8705 specifies client-certificate authentication and certificate-bound access tokens; both the authorization server and resource server must enforce the binding.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Separate the two protections

1. **Mutual-TLS client authentication** proves the client controls a certificate when calling the authorization server. RFC 8705 defines both PKI and self-signed certificate methods.
2. **Certificate-bound access tokens** bind an issued token to a client certificate. The resource server must require mutual TLS and verify the presented certificate matches the token binding.
3. These mechanisms are complementary but can be deployed separately. Do not imply that using mTLS on the token endpoint automatically makes every access token sender-constrained.

## Implementation requirements

1. **Register the expected credential per client.** For PKI mode, validate the configured subject/SAN and certificate chain according to policy. For self-signed mode, register the client certificate/JWK from a controlled source.
2. **Bind the token at issuance.** Include or expose the certificate thumbprint binding using the RFC’s confirmation claim/introspection semantics.
3. **Enforce the same certificate at the API.** The resource server obtains the client certificate from the TLS layer and compares it to the binding. A mismatch must be rejected as an invalid token; never fall back to bearer acceptance for a bound-token route.
4. **Design TLS routing deliberately.** The server must know to request a client certificate during the handshake, before it sees the HTTP authorization header. Use dedicated mTLS hostnames/ports or require mTLS for the relevant resource class.
5. **Plan rotation.** A new certificate invalidates tokens bound to the old certificate. Stage the new credential, acquire new tokens, monitor successful use, then retire the old credential according to the client’s availability requirements.
6. **Protect termination paths.** If a load balancer terminates TLS, the application must receive authenticated certificate identity through a trusted channel. A user-controlled forwarding header is not proof of possession.

## Verification checklist

- A correct token works only with the bound certificate.
- The same token fails with no certificate and with a different certificate.
- Token introspection/local validation exposes and checks the binding consistently.
- Certificate rotation invalidates or refreshes old bindings as designed.
- Logs record client identity and outcome without recording private keys, full certificates unnecessarily, or access tokens.

## Sources

- [RFC 8705: OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html)
- [OAuth 2.0 Security Best Current Practice, RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html)
