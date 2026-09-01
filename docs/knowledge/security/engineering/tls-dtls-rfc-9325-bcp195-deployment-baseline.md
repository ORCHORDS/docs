# TLS and DTLS RFC 9325 Deployment Baseline

**Issue:** TLS and DTLS settings evolve independently across servers, clients, proxies, service meshes, and appliances, leaving deprecated versions, inconsistent algorithms, and undocumented legacy exceptions.

**Date:** 2026-09-01
**Author:** ORCHORDS
**Status:** documented

## Standards context

RFC 9325, published in November 2022, is IETF Best Current Practice 195 for secure use of TLS and DTLS. It obsoletes RFC 7525 and updates earlier RFCs. It establishes TLS 1.2 and DTLS 1.2 as minimum supported baselines and recommends supporting and preferring TLS 1.3 and DTLS 1.3.

A BCP is authoritative current IETF operational guidance, but it is not a product configuration profile. Each implementation, protocol, threat model, and interoperability population still requires tested configuration and documented exceptions.

## Baseline inventory

Maintain an inventory of every component that initiates, terminates, forwards, inspects, or offloads TLS or DTLS. Record:

- service and environment owner;
- client, server, proxy, load balancer, gateway, appliance, or library role;
- implementation and version;
- enabled protocol versions and algorithm policy;
- certificate and trust-store source;
- service-identity validation policy;
- session resumption, early data, client authentication, SNI, and ALPN behavior;
- externally reachable names and ports; and
- approved exceptions with expiry and compensating controls.

Discovery results should be reconciled with configuration records. A successful scanner result for one endpoint does not prove that every regional listener, failover path, or internal client uses the same baseline.

## Protocol-version policy

Enable and prefer TLS 1.3 or DTLS 1.3 where the complete path supports it. Maintain TLS 1.2 or DTLS 1.2 only with an approved algorithm and feature policy. Disable SSL and TLS versions older than 1.2, and disable DTLS 1.0, except under a time-limited, risk-approved compatibility exception.

Do not enable generic version fallback that silently weakens a connection after arbitrary failures. Test downgrade protection across clients, terminators, and middleboxes. A protocol-version exception should identify the exact peer population, replacement plan, telemetry, and removal date.

## Algorithms and key establishment

Use implementation profiles aligned with RFC 9325 and current cryptographic policy. Prefer authenticated encryption and forward-secret key establishment. Remove export, anonymous, null-encryption, static-key-exchange, and other prohibited or obsolete choices.

Treat algorithm names as implementation-specific input that must be resolved to actual negotiated behavior. Test negotiation rather than relying only on a configuration string. Apply key-size, signature-algorithm, certificate-lifetime, and key-rotation requirements consistently across certificates, issuing systems, and trust anchors.

Cryptographic agility does not mean enabling every available algorithm. Maintain a reviewed allowlist and a controlled process for adding, deprecating, and removing choices.

## Certificate and service identity

Validate the certification path, validity, intended usage, revocation policy where applicable, and the service identity expected by the application. Construct reference identifiers from trusted configuration or user intent before connection establishment and apply the relevant application profile.

Certificate issuance or a valid chain alone does not authenticate the intended service. Do not disable hostname or service-identity checks to resolve deployment errors. See the separate RFC 9525 service-identity guidance for identifier matching details.

## Feature controls

- Disable TLS-level compression and review application compression separately for secrets-in-context risks.
- Control renegotiation and post-handshake authentication according to protocol version, implementation support, and application need.
- Bind session resumption to current authorization, certificate, tenant, and policy state.
- Permit TLS 1.3 early data only for explicitly replay-safe operations with replay-aware application controls.
- Validate SNI and ALPN routing so fallback virtual hosts or protocols do not bypass policy.
- Keep random-number generation, nonce construction, and key reuse within implementation and protocol safety requirements.
- Apply consistent settings across clustered or multi-tenant termination points.

## Legacy exception record

Every exception should include the affected peer and business process, unavailable capability, exact weaker setting, exposure, compensating controls, owner, telemetry, migration dependency, approval, and expiry. Revalidate exceptions after client, appliance, certificate, or network changes.

Do not create a global weak listener for a small legacy population when segmentation, a dedicated gateway, or protocol translation can contain the exception.

## Verification

- Enumerate configured and negotiated versions and algorithms from representative clients and network paths.
- Present expired, untrusted, wrong-identity, weak-signature, and incomplete-chain certificates and assert failure.
- Test downgrade, fallback, SNI, ALPN, session resumption, renegotiation, and early-data behavior.
- Compare every load balancer, region, and failover endpoint against the approved baseline.
- Confirm that telemetry identifies negotiated version, broad algorithm class, and failure category without logging keys, session secrets, or sensitive payloads.
- Exercise exception expiry and verify the weak path can be removed without an undocumented dependency.

## Failure modes

- Treating TLS 1.2 support as sufficient without controlling algorithms and features leaves unsafe negotiation paths.
- Enabling TLS 1.3 on servers while old clients or middleboxes force fallback creates a misleading migration claim.
- Disabling certificate verification to fix connectivity removes peer authentication.
- Applying one server scan to all clients, regions, and internal hops leaves blind spots.
- Allowing early data for state-changing operations creates replay risk.
- Keeping permanent legacy cipher exceptions turns temporary compatibility into the effective baseline.
- Copying a generic cipher string without testing the implementation can enable or disable unintended suites.

## Official sources

- [RFC 9325: Recommendations for Secure Use of TLS and DTLS](https://www.rfc-editor.org/rfc/rfc9325.html)
- [BCP 195 information](https://www.rfc-editor.org/info/bcp195)

Source status was checked on September 1, 2026.

## Scope note

This article provides deployment governance, not a complete cryptographic profile or proof of conformance. Application protocols, regulatory requirements, implementation advisories, certificate policy, and current vulnerability guidance can impose additional or newer constraints.
