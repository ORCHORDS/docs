---
title: "TLS Certificate Revocation Response"
owner: "Identity and Access Management"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Private key compromise, CA compromise, certificate mis-issuance, or discovery of a certificate used outside documented policy."
scope: "All TLS certificates issued by ORCHORDS-controlled or partner CAs for internal and customer-facing services."
inputs:
  - "Certificate inventory and revocation infrastructure"
  - "Compromise evidence or scope of mis-issuance"
  - "Service map showing certificate deployment"
  - "CRL and OCSP responder configuration"
plan:
  - "Step 1: Receive the revocation trigger and capture certificate identifier, scope, and rationale."
  - "Step 2: Confirm the scope of compromise and identify every service and consumer affected."
  - "Step 3: Issue a CRL update and refresh the OCSP responder within the documented SLA."
  - "Step 4: Replace the certificate on every affected endpoint and roll out through the standard change control process."
  - "Step 5: Force re-issuance from a controlled source with a new key pair; do not re-use the compromised key."
  - "Step 6: Communicate to consumers with the documented notice and the new certificate details."
  - "Step 7: Capture residual actions and feed the incident into the post-incident review pipeline."
evidence:
  - "Revocation record with timestamps and rationale"
  - "Service map of affected endpoints"
  - "CRL and OCSP refresh log"
  - "Replacement certificate deployment records"
  - "Consumer communication record"
escalation:
  - "Compromise of CA root or sub-CA — escalate to Information Security Officer within 30 minutes."
  - "Customer-facing certificate with active exploitation — escalate to Security on-call and Service Owner."
completion:
  - "Compromised certificate revoked in CRL and OCSP within SLA."
  - "Replacement deployed to every affected endpoint."
  - "Consumer communication sent."
exceptions:
  - "Certificates with planned expiry within the documented grace window; coordinated replacement within 24 hours."
related:
  - "PUBLIC_KEY_INFRASTRUCTURE_REVIEW.md"
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "CHANGE_CONTROL.md"
