---
title: "Certificate Lifecycle Management Playbook"
owner: "PKI Owner"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Certificate Lifecycle Management Playbook

## Trigger

Use this playbook when TLS, code signing, S/MIME, client authentication, IoT, or other X.509 certificates must be requested, issued, renewed, re-keyed, revoked, or replaced, or when an audit, vulnerability, or expiry incident requires coordinated certificate action.

## Scope

Apply the process to all internal and publicly trusted certificates across the organization, including those issued by internal CAs, ACME-issued certificates (Let's Encrypt, internal ACME hierarchies), commercial CAs, and the corresponding keys and chain material.

## Inputs

- certificate inventory entry (subject, SANs, issuer, expiry);
- deployed location (load balancer, application, device, service mesh);
- renewal, re-key, or revocation trigger;
- crypto-agility constraints (algorithm, key length, signature);
- applicable policy (CP/CPS, organizational cipher policy).

## Steps

1. **Identify scope.** Confirm the certificate, its location, the issuance authority, the consumers, and the expiry window.
2. **Select issuance path.** Choose ACME for automation where supported, an internal CA for internal services, or a commercial CA for publicly trusted certificates.
3. **Generate or accept the key pair.** For server-generated keys, use a validated cryptographic module; for CA-issued keys, ensure secure key delivery.
4. **Submit the certificate signing request (CSR).** Provide the CSR with subject, SANs, key usage, EKU, validity period; for ACME, complete the challenge (HTTP-01, DNS-01, or TLS-ALPN-01).
5. **Validate the issued certificate.** Verify chain, key usage, EKU, signature algorithm, validity period, CT logs (for public), and revocation information (CRL/OCSP).
6. **Deploy the certificate and chain.** Install certificate, chain, and key on the target; restart or reload as required; verify TLS handshake and that the chain resolves to a trusted root.
7. **Schedule renewal and verification.** Track not-before and not-after timestamps; configure automated renewal where supported; validate renewal on a scheduled basis.
8. **Revoke on trigger.** Revoke immediately on key compromise, certificate misuse, subject change, or CA incident; update CRL and OCSP responders; notify affected relying parties.
9. **Replace.** When retiring a certificate, ensure consumers migrate to the new certificate before the old one expires or is revoked.
10. **Audit and report.** Log issuance, renewal, revocation, and key events; reconcile counts during internal and external audits; report compliance to PKI Owner.

## Escalation

Escalate to the PKI Owner and Security when:
- a private key is suspected of compromise;
- a certificate is mis-issued or used outside policy;
- expiry exceeds the documented tolerance window;
- a CA certificate is compromised or under scrutiny.

## Evidence

- certificate inventory record and CSRs;
- issuance and renewal logs from CA and ACME;
- deployment verification (handshake, trust chain);
- revocation and OCSP/CRL records;
- audit reconciliation and exception reports.

## Completion Criteria

The lifecycle event is considered complete when:
- the certificate is correctly issued, deployed, and verified;
- renewal, revocation, or replacement schedule is recorded;
- audit records are reconciled and retained;
- relying parties are notified where required.

## Exceptions

Document deviations from policy with the technical justification, scope, expiration, compensating control, and review schedule. Long-lived internal certificates or non-renewable legacy devices require compensating controls.

## Related Documents

- [Public Key Infrastructure Operations Response](PUBLIC_KEY_INFRASTRUCTURE_OPERATIONS_RESPONSE.md)
- [RFC 5280 X.509 PKI Profile](../reference/RFC_5280_X509_PKI_PROFILE.md)
- [RFC 8555 ACME Profile](../reference/RFC_8555_ACME_PROFILE.md)
- [NIST SP 800-52 Guidelines for TLS Implementations](NIST_SP_800_52_TLS_GUIDELINES.md)
