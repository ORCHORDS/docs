---
title: Ceph Distributed Storage Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://docs.ceph.com ; https://github.com/ceph/ceph ; https://rook.io
---

# Ceph Distributed Storage Version Governance

## 1. Purpose

This reference card defines the version-governance model for the Ceph distributed storage system when deployed as a substrate for block (RBD), object (RGW), and filesystem (CephFS) workloads. It applies to self-managed Ceph clusters (often via Rook on Kubernetes), Cephadm-deployed clusters, and managed services that expose a Ceph-compatible API.

## 2. Scope

In scope:

- **Ceph** releases in the **Reef** (18.x) and **Squid** (19.x) LTS tracks.
- **Rook-Ceph** Operator ≥ 1.14.
- **Cephadm** ≥ Reef for non-Kubernetes deployments.
- RBD, RGW (including S3-compatible API and S3 Select), and CephFS clients.
- Multi-site RGW federation (active-active and active-passive).

Out of scope:

- Legacy Luminous (12.x) and Nautilus (14.x) deployments — end-of-life and unsupported.
- Custom backends outside the canonical BlueStore.

## 3. Versioning policy

- Pin the Ceph container images to a specific point release (e.g. `v18.2.4`) and digest; never float on `:latest`.
- Run a **minimum of 5 monitors** and **7 OSD hosts** for production clusters to maintain quorum and CRUSH map resilience.
- BlueStore is the only supported OSD backend; FileStore is deprecated.
- CephFS requires a dedicated metadata pool with `pg_autoscale_mode = on`.

## 4. Compatibility matrix

| Ceph | Kubernetes (Rook) | RGW S3 API | Notes |
| --- | --- | --- | --- |
| Reef 18.2.x | 1.27+ | 2006-09-01 | S3 Select GA, RGW multi-site sync v2 |
| Squid 19.2.x | 1.30+ | 2006-09-01 | Improved erasure coding profiles, faster recovery |

## 5. Capacity and CRUSH planning

- Maintain at least 3 replicas for `replicated` pools; for erasure-coded pools, use `k=4, m=2` minimum.
- Configure CRUSH rules per failure domain (host, rack, room, zone). Multi-site deployments require distinct CRUSH rules per site.
- Set `mon_osd_full_ratio = 0.85` and `mon_osd_nearfull_ratio = 0.70` to give operators runway before writes are blocked.

## 6. Upgrade procedure

1. Upgrade monitors first (`ceph orch upgrade start --image <digest>`), one at a time, and wait for `ceph -s` to show healthy between each.
2. Upgrade managers, then RGW, then OSDs (rolling, one host at a time).
3. Verify `ceph -s` reports `health: HEALTH_OK` and `pg: active+clean` throughout.
4. Run `ceph config set osd_nautilus_compat` and the Reef/Squid feature toggles as documented for the source version.

## 7. Rollback procedure

- Ceph upgrades are **not natively reversible** for OSDs; preserve a snapshot of the OSD data directory before any OSD upgrade.
- For monitor and manager rollbacks, `ceph orch upgrade --stop` and re-deploy the previous version.
- For CRUSH map regressions, restore the previous `crushmap.bin` from the backup taken pre-upgrade.

## 8. Observability

- Required metrics: `ceph_health_status{state}`, `ceph_pool_used_bytes`, `ceph_osd_op_latency_seconds{op}`, `ceph_rgw_request_total{status}`.
- Alert on `ceph_health_status{state="HEALTH_ERR"} == 1` and on `ceph_pool_used_bytes / ceph_pool_total_bytes > 0.85`.

## 9. References

- Ceph release notes — https://docs.ceph.com/en/latest/releases/
- Rook-Ceph documentation — https://rook.io/docs/rook/latest/ceph-storage.html
- Ceph multi-site RGW — https://docs.ceph.com/en/latest/radosgw/multisite/
