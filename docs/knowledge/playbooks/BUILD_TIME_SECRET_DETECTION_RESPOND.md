---
title: "Build Time Secret Detection Response"
owner: "Supply Chain Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "30 days"
next-review: "2026-10-05"
trigger: "Build-time secret detection alert, pull request scanner finding, or post-commit secret exposure."
scope: "All source repositories, build pipelines, and container image builds under ORCHORDS management."
inputs:
  - "Secret detection alert with file, line, and rule identifier"
  - "Repository and branch context"
  - "Build pipeline and image build records"
  - "Secret classification and rotation policy"
plan:
  - "Step 1: Receive the alert and capture repository, branch, commit, file, line, and rule identifier."
  - "Step 2: Classify the secret: provider credential, internal API key, signing key, personal access token, or test fixture."
  - "Step 3: Revoke the secret at the issuing system; record the revocation timestamp and the revoking operator."
  - "Step 4: Purge the secret from the repository history using the documented history-rewrite procedure; coordinate with the repository owner."
  - "Step 5: Re-issue the secret through the documented issuance process; update any consumers of the secret."
  - "Step 6: Audit logs and access records from the issuing system for unauthorized use of the secret during the exposure window."
  - "Step 7: Open a remediation ticket for the build pipeline or contributor education if the exposure is recurrent."
evidence:
  - "Alert record with full context"
  - "Secret classification and revocation record"
  - "History purge record"
  - "Issuance and consumer update record"
  - "Unauthorized use audit"
escalation:
  - "Provider credential with confirmed unauthorized use — escalate to Security on-call within 30 minutes."
  - "Signing key with potential signature forgery — escalate to Security on-call and follow PUBLIC_KEY_INFRASTRUCTURE_REVIEW.md."
completion:
  - "Secret revoked at the issuing system."
  - "Repository history purged or risk-accepted with compensating control."
  - "Unauthorized use audit completed."
exceptions:
  - "Documented test fixtures that match real patterns but are non-functional."
related:
  - "PUBLIC_KEY_INFRASTRUCTURE_REVIEW.md"
  - "CREDENTIAL_COMPROMISE_RESPONSE.md"
  - "SECRETS_ROTATION_DRIFT_REVIEW.md"
