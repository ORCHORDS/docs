# SPIRE Federation Setup Playbook

## Purpose

Establish bidirectional trust between two SPIRE deployments (typically across clusters, regions, or organizations) so that workloads in one trust domain can authenticate workloads in another using a federated X.509-SVID or JWT-SVID.

## Audience

Platform engineers, security engineers, cluster operators on both SPIRE deployments.

## Pre-conditions

- Both SPIRE Server clusters running ≥ 1.7.x with HA Raft consensus (3 or 5 nodes).
- Network connectivity on the SPIRE Server federation port (default 8443) between the two deployments.
- Mutual TLS or IP allow-list restricting federation endpoints to known SPIRE Server IPs.
- An out-of-band channel for exchanging the initial trust bundle (e.g. PGP-signed email or a trusted internal artefact store).

## Procedure

1. **Generate the trust bundle on each side**:
   `spire-server bundle show -format spiffe_json > /tmp/bundle-a.json` (deployment A)
   `spire-server bundle show -format spiffe_json > /tmp/bundle-b.json` (deployment B)
2. **Exchange bundles out-of-band** and validate JSON signatures before importing.
3. **Apply the peer bundle**:
   `spire-server bundle set -bundle /tmp/bundle-a.json` (on deployment B, sets trust domain A)
   `spire-server bundle set -bundle /tmp/bundle-b.json` (on deployment A, sets trust domain B)
4. **Configure the federation block** in each SPIRE Server's `conf/server/server.conf`:
   ```hcl
   federation {
     bundle_endpoint {
       address = "0.0.0.0:8443"
       attestation_allow_list {
         spiffe_id = "spiffe://<peer-trust-domain>/spire/server"
       }
     }
     federated_bundle_cleanup_timeout = "10m"
   }
   ```
5. **Restart SPIRE Servers** to apply the configuration. Verify with `spire-server federation list`.
6. **Smoke test**:
   - On deployment A, issue a workload identity for a canary service in trust domain A.
   - From deployment B, attempt to verify the federated X.509-SVID against the imported bundle.
   - Validate JWT-SVID flow for cross-domain API calls (e.g. tenant A workload calls tenant B endpoint).
7. **Document**: record the federation topology, peer endpoints, and the schedule for trust-bundle rotation in `policies/spire-federation/`.

## Rollback

- Remove the federation block from both `server.conf` files and restart.
- On each deployment, run `spire-server bundle delete -trust-domain <peer>` to drop the imported trust bundle.
- Restart any workloads that hold long-lived X.509-SVIDs cached before the rollback; SPIRE will issue new SVIDs from the local trust bundle only.

## References

- SPIRE federation documentation — https://spiffe.io/docs/latest/spire/using/federation/
- Internal: Batch 99 reference card `SPIFFE_SPIRE_VERSION_GOVERNANCE.md`.
