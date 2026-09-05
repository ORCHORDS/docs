# Envoy Listener Hot Reload Playbook

## Purpose

Define the operational procedure for safely reloading Envoy listener configuration without dropping in-flight connections. The procedure covers both LDS (Listener Discovery Service) hot reload and full restart scenarios.

## Audience

Platform engineers, SREs, and gateway operators.

## Pre-conditions

- Envoy 1.25+ (per `ENVOY_VERSION_GOVERNANCE.md`).
- The Envoy instance is part of an xDS-managed fleet OR a self-managed fleet.
- Hot restart is enabled.

## Procedure

### Step 1 — Detect

1. Confirm the listener config drift: `curl localhost:9901/config_dump | jq '.configs[1].dynamic_active_clusters'`.
2. Confirm the listener is accepting connections: `curl localhost:9901/ready`.

### Step 2 — Author the new config

3. Edit the bootstrap or LDS source.
4. Validate locally: `envoy --mode validate -c <config-path>`.
5. If using SOTW (State of the World) xDS, prepare a new snapshot.

### Step 3 — Hot reload via LDS

6. Send the new Listener via xDS:
   - `curl -X POST localhost:9901/listeners/<name>` (rare).
   - Or push via the control plane: `envoy-xds <snapshot>`.
7. Confirm the new listener is `warming`.
8. Confirm Envoy drains old connections via `admin.early_header_conn_end`.

### Step 4 — Hot reload via full restart

9. If hot reload is not feasible, perform a hot restart:
   - `systemctl reload envoy` (sends SIGHUP, hot restart).
   - Confirm the parent and child processes are running.
   - Confirm the old listener drains over `drain_timeout`.

### Step 5 — Verify

10. Confirm new connections are accepted.
11. Confirm in-flight connections continue.
12. Confirm metrics show the listener is healthy.

### Step 6 — Validate

13. Send a synthetic HTTP request.
14. Confirm response matches the new config.
15. Confirm headers / routes / filters behave as expected.

### Step 7 — Monitor

16. Confirm 5xx rate is at baseline.
17. Confirm connection error rate is at baseline.
18. Confirm listener accept rate matches expected traffic.

## Rollback

If the new listener config breaks traffic:

1. Hot-restart Envoy to the previous config.
2. If a full restart, restore the previous binary and config.
3. Validate traffic recovery.

## References

- `ENVOY_VERSION_GOVERNANCE.md`
- `GITOPS_SYNC_FAILURE_RECOVERY_PLAYBOOK.md`
- Envoy hot restart: `https://www.envoyproxy.io/docs/envoy/latest/operations/hot_restarter`
- Envoy admin: `https://www.envoyproxy.io/docs/envoy/latest/operations/admin`
