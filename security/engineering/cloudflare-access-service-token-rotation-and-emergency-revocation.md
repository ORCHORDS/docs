# Cloudflare Access service-token rotation and emergency revocation

**Category:** Security
**Author:** ORCHORDS
**Primary source:** [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)

## Problem

A machine-to-machine credential can remain valid even after application sessions are revoked. Treating a client secret as a session token can leave an unwanted service principal active during an incident.

## Operational model

- Create service tokens with a named owner, narrowly scoped Access policy, expiry, and rotation date.
- Record the client ID in configuration and store the client secret only in the workload's secret store. Cloudflare displays the secret only at creation.
- Rotate with overlap: create a successor, deploy it, verify a fresh request, then remove the old secret from workloads.
- Emergency revocation requires deleting the service token; revoking application sessions alone does not invalidate its client ID and secret.
- Alert before expiry and maintain an incident runbook that identifies the owning service and dependent deployments.

## Verification

1. Prove a request using the new token reaches only the intended application.
2. Remove the old credential and confirm an old-token request is rejected.
3. Revoke application sessions during a test and confirm this does not substitute for service-token revocation.
4. Review Access logs for the expected client ID during rollout.

## Failure modes

- Rotation without overlap causes avoidable outages.
- Session revocation is mistaken for machine-credential revocation.
- A broadly scoped, ownerless service token becomes an untraceable long-lived access path.

## Related

- [Cloudflare Access service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
