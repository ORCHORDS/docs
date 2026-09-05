# Workload Identity Rotation Playbook

## Purpose

Standardise the procedure for rotating SPIFFE/SPIRE, AWS IRSA, GCP Workload Identity, or Azure Workload Identity credentials across an ORCHORDS cloud-native estate without causing service outages. The play covers planned rotations, incident-driven rotations, and emergency rotations following a trust-store compromise.

## Procedure

1. **Identify the workload identity surface area.**
   - SPIRE: enumerate workloads, federation trusts, and trust domains with `spire-server workload show` and `spire-agent api fetch`.
   - AWS IRSA: `aws iam list-roles --query 'Roles[?AssumeRolePolicyDocument.Statement[?PrincipalType==`Service` && Principal.Service==`eks.amazonaws.com`]]'`.
   - Azure MI: `az identity list` and `az aks show --query "identityProfile"`.
   - GCP WI: `gcloud iam service-accounts keys list` and workload identity bindings.
2. **Confirm rotation window.** Validate SLO budgets (NIST SP 800-53 SI-7 + internal SLO board) before proceeding. Schedule during the lowest-traffic window; if emergency, see step 8.
3. **Pre-rotation validation.** Run a no-op "test rotation" that only issues a new SVID/certificate without revoking the old one; observe workload behaviour for at least one full interval.
4. **Issue new identity artefacts.**
   - SPIRE: rotate server CA + agent SVIDs; for short-lived SVIDs this is automatic; for long-lived, force a re-issue.
   - IRSA: rotate the OIDC provider thumbprint via `aws iam update-open-id-connect-provider-thumbprint` if the upstream IdP rotated keys.
   - Azure MI: trigger a version bump with `az identity federated-credential update` for each federated workload.
   - GCP WI: re-issue the GoogleServiceAccount key via `gcloud iam service-accounts keys create` and update Workload Identity binding.
5. **Dual-broadcast window.** Run with both old and new credentials valid for the rotation window (typically 1–4× SVID TTL, or one SLO interval). Monitor the issuer rate of new vs. old.
6. **Cutover.** Switch all workload manifests/CSI mounts/secret references to the new identity. Verify identity can authenticate against all backing services (database, cache, queue, object store).
7. **Revoke old identity.** Once cutover is confirmed (≥ one full rollout interval with no fallbacks), revoke old SPIFFE ID, delete old IRSA trust, remove federated credential, etc.
8. **Emergency rotation.** Skip pre-rotation validation if a compromise is suspected. Issue new identity, broadcast dual-window for ≤ 15 minutes, cutover, revoke old within the same window. Page on-call security on-call + SRE principal.
9. **Verify and audit.** Run `spire-server bundle show` / IAM credential reports / Azure AD sign-in logs / GCP audit logs to confirm only the new identity is in use. Archive the rotation event with timestamp, operator, and rationale.
10. **Record in the rotation ledger.** Update the workload-identity inventory system with the new fingerprint, expiry, and the previous fingerprint chain for rollback reference.
