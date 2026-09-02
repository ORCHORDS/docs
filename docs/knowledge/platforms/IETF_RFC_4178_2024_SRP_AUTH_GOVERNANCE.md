# IETF RFC 4178:2024 SRP Authentication Governance

## Purpose

IETF RFC 4178, "Simple Password Authentication," defines the Secure Remote Password (SRP) protocol, a password-authenticated key agreement (PAKE) protocol that allows a user to authenticate to a server using a password without transmitting the password (or any value from which the password can be derived) over the network. SRP-6a is the variant most widely deployed. This article governs the application of RFC 4178 / SRP in protocols and applications where password authentication is required and where the password must not traverse the network in any recoverable form.

## Scope

The specification applies to protocols and applications that require password-based authentication. Within this knowledge base, the article covers the SRP-6a flow, the parameter selection (safe prime, generator), the verifier storage, the hash function, the multi-party key derivation, and the integration with the application's authentication framework. It does not cover the broader TLS handshake; SRP is typically used as an authentication layer within TLS or another protected channel.

## Workflow

1. Generate or adopt a safe prime N and a generator g. The parameters must be N and g from a known safe-prime group; RFC 5054 publishes one such group and additional groups are cataloged elsewhere. The modulus must be a safe prime.
2. Choose a strong hash function (SHA-256 or stronger) and use it consistently.
3. On the server, store the verifier v = g^x mod N, where x = H(salt || H(username || ":" || password)). The verifier is the credential; if the server is compromised, the verifier is what an attacker gains, and it must be derived from a strong hash to resist offline brute force.
4. Use a per-user salt to prevent verifier reuse attacks.
5. Implement the SRP-6a exchange:
   - Client sends username, A = g^a mod N.
   - Server sends salt s, and B = kv + g^b mod N (k = H(N || g) is a multiplier that detects weak parameters).
   - Client computes x, u = H(A || B), S = (B - kg^x)^(a + ux) mod N.
   - Server computes S = (Av^u)^b mod N.
   - Both compute K = H(S) as the session key, and exchange M1 and M2 to confirm mutual authentication.
6. Derive any session keys the application needs from the agreed shared secret.
7. Document the SRP parameters, the hash function, and the verifier storage.

## Controls and evidence

SRP controls include the parameter choice, the verifier storage, the salt, and the integration with the authentication framework. Evidence includes the documented parameter set, the verifier storage implementation, the test vectors the implementation passes, and the authentication audit logs.

## Validation

Validation should confirm the parameters are from a known safe-prime group, the verifier is stored correctly, the exchange produces the agreed key on both sides, the mutual authentication confirms, and the session key is used appropriately. Test vectors from RFC 5054 and from project test suites confirm the implementation.

## Failure correction

Common failure modes: weak primes are used (correct: use a known safe-prime group from a reputable source); verifier is stored as a hash without salt (correct: use a per-user salt); the exchange is implemented without the k multiplier (correct: include k = H(N || g) to detect weak parameters); mutual authentication is not confirmed (correct: exchange M1/M2 and check them); session key is not used for confidentiality of subsequent traffic (correct: use the session key for an authenticated encryption layer).

## Limitations

RFC 4178 defines SRP-6a; it does not certify any specific implementation. The protocol's security depends on the choice of parameters, the verifier storage security, and the implementation correctness. SRP is not immune to phishing or to endpoint compromise; it protects the password in transit, not against all threats.

## Scope note

This article summarizes project-neutral platform use of IETF RFC 4178 / SRP-6a. It does not assert any specific deployment's conformance or claim any certification outcome.

## Canonical sources

- IETF RFC 4178 — Simple Password Authentication: https://www.rfc-editor.org/rfc/rfc4178
- IETF RFC 5054 — Using SRP for TLS Authentication: https://www.rfc-editor.org/rfc/rfc5054