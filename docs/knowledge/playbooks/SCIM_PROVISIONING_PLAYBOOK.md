# SCIM 2.0 User Provisioning Playbook

## Purpose

Stand up SCIM 2.0 between an authoritative source of identity such as Workday or an HR system and downstream applications using the IdP broker pattern. Establish automated joiner, mover, and leaver lifecycle management, enforce least privilege through group and entitlement mapping, and guarantee timely deprovisioning on termination events. Maintain a complete, tamper-resistant audit trail of every identity state change for compliance and forensics.

## Audience

IAM engineers, identity architects, HR integration engineers, platform engineers.

## Pre-conditions

- Authoritative HR system is the system of record for employee lifecycle events and emits normalized identity records.
- IdP exposes a SCIM 2.0 `/Users`, `/Groups`, `/Bulk`, `/ServiceProviderConfig`, and `/Schemas` endpoint set.
- OAuth client credentials are minted with the `scim` scope and bound to a dedicated service principal.
- Mutual TLS is supported on both the IdP and downstream RP endpoints with pinned CA bundles.
- Webhook delivery endpoint is reachable, signature-verified, and idempotent.
- Observability stack ingests SCIM request and response metrics, error codes, and latencies.
- Centralized audit log destination is online with retention and integrity controls applied.

## Procedure

1. Issue a dedicated OAuth client with the `scim` scope and rotate keys via OAuth 2.1 dynamic client registration; record client metadata in the secrets vault.
2. Configure the IdP SCIM endpoint URL, declare SCIM protocol version 2.0, and advertise supported features in `/ServiceProviderConfig` and resource definitions in `/Schemas`.
3. Map authoritative HR user attributes to SCIM core `User` schema fields (`userName`, `name`, `emails`, `active`, `externalId`) and required enterprise extension attributes (`employeeNumber`, `department`, `costCenter`, `manager`).
4. Define `Group` to role mappings and resolve entitlement grants using schema URIs and display names; capture membership semantics (`direct`, `indirect`).
5. Configure push notification (webhook) for change events and pull polling via `/Users` with SCIM filters (`filter`, `attributes`, `excludedAttributes`) for reconciliation.
6. Schedule bulk sync operations on a fixed cadence; track state using `startId`, `startIndex`, and ETags for optimistic concurrency and conflict resolution.
7. Configure `PATCH` semantics for incremental attribute updates and `PUT` for full resource replacement; respect mutability per RFC 7643.
8. Wire automated deprovisioning on HR termination events by setting `active=false`, revoking sessions, and triggering `DELETE` after the grace window.
9. Validate idempotency on bulk operations using `bulkId`, request fingerprints, and replay-safe duplicate detection.
10. Capture lifecycle event records (request, response, actor, client, outcome, correlation identifier) to the audit log with integrity hashing.
11. Test with synthetic joiner, mover, and leaver scenarios including duplicate external identifiers, attribute conflicts, and suspension overrides.
12. Promote to staging then production behind feature flags; enable targeted tenants, monitor error budgets, and graduate to full rollout.

## Rollback

Disable the SCIM client at the IdP, revert to manual provisioning for affected applications, drain in-flight bulk requests by completing or rejecting active batches, and revoke all issued OAuth tokens and signing certificates. Notify downstream RPs to suspend SCIM-fed accounts pending manual reconciliation, then preserve audit and webhook logs for post-incident review.

## References

- [SCIM 2.0 Version Governance](../reference/SCIM_2_0_VERSION_GOVERNANCE.md)
- [Keycloak Version Governance](../reference/KEYCLOAK_VERSION_GOVERNANCE.md)
- [OAuth 2.1 Version Governance](../reference/OAUTH_2_1_VERSION_GOVERNANCE.md)
