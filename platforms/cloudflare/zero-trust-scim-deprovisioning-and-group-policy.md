# zero-trust-scim-deprovisioning-and-group-policy

**Issue:** Cloudflare Zero Trust access depends on identity-provider groups, but leavers, group removals, rehires, and provisioning failures are not tested as access-lifecycle events.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

SCIM synchronization and identity login are separate lifecycle signals. Group membership is an authorization input only when the IdP, provisioning configuration, and Cloudflare Access policy remain aligned. A user who is removed or rehired needs an explicit, auditable lifecycle outcome.

**Source:** [Cloudflare SCIM](https://developers.cloudflare.com/cloudflare-one/team-and-resources/path/to/).

## Fix

- treat the IdP as the owned source of truth for managed users/groups;
- map groups to narrowly scoped Access policies with documented owners;
- test deprovisioning, group removal, rehire, and sync failure behavior;
- review access/audit events and alert on provisioning errors;
- separate dashboard-administrator lifecycle from end-user application access;
- retain evidence of high-risk access changes without logging identity secrets.

## Verification

- A removed user loses intended access within the documented lifecycle.
- Group removal changes policy outcome as expected.
- A rehire is not silently restored beyond the current group policy.
- SCIM failure produces an owned alert and reconciliation task.

## Related

- `cloudflare/zero-trust-access.md`
- `security/scim-20-2026.md`
