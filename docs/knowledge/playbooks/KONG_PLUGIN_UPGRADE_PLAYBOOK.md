# Kong Plugin Upgrade Playbook

## Purpose

Define the operational procedure for upgrading a Kong plugin (built-in or custom) without service disruption. The procedure covers DB and DB-less modes, including plugin configuration changes.

## Audience

Platform engineers, SREs, and gateway operators.

## Pre-conditions

- Kong 3.x (per `KONG_VERSION_GOVERNANCE.md`).
- The Kong instance is in DB or DB-less mode.
- The team has a GitOps-managed configuration.

## Procedure

### Step 1 — Detect

1. Confirm the current plugin version: `curl localhost:8001/plugins/<plugin-id>`.
2. Confirm the upgrade target is documented in the Kong changelog.

### Step 2 — Validate the upgrade

3. Read the plugin changelog.
4. Identify breaking changes (config schema, behavior).
5. Test in a non-production environment.

### Step 3 — Update the configuration

6. Update the plugin config in `kong.yaml` or `decK` file.
7. Run `deck diff` to preview changes.
8. Run `deck sync` to apply (DB-less) or `deck sync` with `pg` connection.

### Step 4 — Reload Kong

9. Reload Kong:
   - `kong reload` (sends SIGHUP).
   - `curl -X POST localhost:8001/config?check_hash=<hash>` (DB-less reload).
10. Confirm the new plugin config is active: `curl localhost:8001/plugins/<id>`.

### Step 5 — Verify

11. Send a synthetic request.
12. Confirm the plugin behavior matches expectations.
13. Confirm metrics (if any) reflect the new plugin.

### Step 6 — Monitor

14. Confirm 5xx rate is at baseline.
15. Confirm latency is at baseline.
16. Confirm error rate is at baseline.

## Rollback

If the plugin upgrade breaks traffic:

1. Revert the Kong config to the previous version.
2. Reload Kong.
3. Confirm traffic recovery.

## References

- `KONG_VERSION_GOVERNANCE.md`
- `GITOPS_SYNC_FAILURE_RECOVERY_PLAYBOOK.md`
- Kong decK: `https://docs.konghq.com/deck/latest/`
- Kong plugins: `https://docs.konghq.com/hub/`
- Kong DB-less: `https://docs.konghq.com/gateway/latest/production/deployment-topologies/db-less/`
