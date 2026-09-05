---
title: "Public Key Infrastructure Review"
owner: "Identity and Access Management"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
trigger: "Six-monthly review, new certificate authority onboarding, key ceremony event, or PKI-related incident."
scope: "All public and private certificate authorities used for internal services, customer-facing services, code signing, document signing, and mutual TLS."
inputs:
  - "CA inventory and hierarchy"
  - "Certificate inventory by issuer and use case"
  - "Key ceremony logs and HSM inventory"
  - "CRL and OCSP responder configuration"
  - "Policy and CPS documents"
plan:
  - "Step 1: Confirm scope and CA hierarchy; verify offline root CA is air-gapped and documented."
  - "Step 2: Verify certificate inventory: count, issuer, subject, validity, key type, and intended use."
  - "Step 3: Verify revocation infrastructure: CRL freshness, OCSP responder health, and revocation status for known-compromised certificates."
  - "Step 4: Verify HSM inventory: location, firmware, access list, and tamper evidence; confirm key ceremonies are logged and dual-control attested."
  - "Step 5: Verify policy documents and CPS against the latest baseline; record deviations for risk acceptance."
  - "Step 6: Verify certificate issuance automation: ACME or internal SCEP enrollment, short-lived certificates, and documented exception process."
  - "Step 7: Capture residual actions and report metrics to governance."
evidence:
  - "CA and certificate inventory snapshots"
  - "Revocation infrastructure health report"
  - "HSM inventory and ceremony logs"
  - "Policy and CPS review report"
  - "Metrics dashboard export"
escalation:
  - "Offline root CA air-gap failure — escalate to Information Security Officer."
  - "Compromised private key with no revocation within SLA — escalate to Security on-call."
completion:
  - "All CAs reviewed and attested."
  - "Revocation infrastructure verified."
  - "HSM inventory and ceremonies verified."
exceptions:
  - "Public CAs operated by external providers reviewed annually through their published audit reports."
related:
  - "ACCESS_REVIEW.md"
  - "CRYPTO_MODULE_INVENTORY_REVIEW.md"
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
