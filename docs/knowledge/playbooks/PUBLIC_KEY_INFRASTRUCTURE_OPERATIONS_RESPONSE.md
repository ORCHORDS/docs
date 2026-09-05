---
title: "Public Key Infrastructure Operations Playbook"
owner: "PKI Owner"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Public Key Infrastructure Operations Playbook

## Trigger

Use this playbook when internal or publicly trusted certificates must be requested, issued, renewed, revoked, audited, or when an incident affects certificate authority (CA) trust, key material, or certificate lifecycle integrity.

## Scope

Apply the process to root CAs, intermediate CAs, issuing CAs, end-entity certificates (TLS, code signing, S/MIME, client authentication, IoT), OCSP and CRL responders, ACME services, and supporting key-management infrastructure (HSMs, key vaults, smart cards).

## Inputs

- certificate policy (CP) and certification practice statement (CPS);
- CA hierarchy and trust chain documentation;
- certificate request including subject, SAN, key usage, EKU, validity period;
- revocation and incident records;
- audit and compliance reports (WebTrust, ETSI, internal).

## Steps

1. **Confirm policy alignment.** Verify the request conforms to the CP/CPS, approved profiles, key type, key length, signature algorithm, validity period, and permitted subject naming conventions.
2. **Validate identity.** Apply the identity proofing procedure appropriate to the assurance level (DV, OV, EV, or internal equivalent); record the proofing evidence and the validator.
3. **Generate or accept the key pair.** Generate keys in a FIPS 140-2/3 validated cryptographic module or HSM; for subscriber keys, securely deliver key material only to the verified requester.
4. **Sign the certificate with a qualified issuer.** Use the issuing CA whose trust scope covers the requested usage; enforce profile enforcement at issuance to reject non-conformant requests.
5. **Publish and distribute.** Publish the certificate to the certificate transparency log where applicable; distribute to the relying parties through automated renewal channels (ACME, SCEP, EST, internal issuance APIs).
6. **Track validity and renewal.** Monitor not-before and not-after dates; renew with sufficient lead time to absorb CA chain changes; track renewals as identity changes only when the subject truly changes.
7. **Revoke on trigger.** Revoke immediately on private key compromise, CA compromise, subject termination, incorrect issuance, or cessation of operation; generate CRL entries and update OCSP responders.
8. **Maintain OCSP and CRL freshness.** Ensure OCSP responder availability and CRL next-update validity are within CP/CPS limits; monitor responder health.
9. **Audit continuously.** Record issuance, renewal, revocation, and key management events in tamper-evident logs; reconcile counts and certificate serial ranges during internal audits.
10. **Respond to CA incidents.** Treat any CA key compromise, mis-issuance, or unauthorized issuance as a trust anchor incident; revoke the affected CA, notify relying parties, and re-issue from a new chain.

## Escalation

Escalate to the PKI Owner, Security Officer, and Legal/Compliance when:
- a private key is suspected of compromise;
- a CA certificate is mis-issued or used outside policy;
- the OCSP responder or CRL distribution point is unreachable beyond tolerance;
- an external audit identifies a non-conformity.

## Evidence

- issuance and revocation logs with serial numbers and timestamps;
- CP/CPS version, audit trail, and policy overrides;
- OCSP responder and CRL distribution point health records;
- HSM access logs and key ceremony records;
- CT log inclusion proofs for public certificates.

## Completion Criteria

PKI operations are considered complete for a given event when:
- the certificate is issued, renewed, or revoked per policy;
- OCSP and CRL reflect the new state;
- audit records are reconciled and retained;
- the relying parties are notified where required.

## Exceptions

Document deviations from CP/CPS with the approver identity, scope, expiration, compensating controls, and review schedule. Track exceptions through resolution.

## Related Documents

- [CA/Browser Forum Baseline Requirements](../reference/CA_BROWSER_FORUM_BASELINE_REQUIREMENTS.md)
- [NIST SP 800-57 Key Management](../reference/NIST_SP_800_57_KEY_MANAGEMENT.md)
- [RFC 5280 X.509 PKI Profile](../reference/RFC_5280_X509_PKI_PROFILE.md)
- [RFC 6960 OCSP Profile](../reference/RFC_6960_OCSP_PROFILE.md)
- [RFC 8555 ACME Profile](../reference/RFC_8555_ACME_PROFILE.md)
