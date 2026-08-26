# Alertmanager HA duplicate-notification contract

**Issue:** An Alertmanager cluster is treated as an exactly-once notification service, so duplicate pages during a partition are misdiagnosed or a load balancer creates a single ingestion failure domain.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Configure each Prometheus server to send alerts to every Alertmanager instance. Do not place a load balancer between Prometheus and the Alertmanager cluster.
- Run peers with the same routing configuration and cluster them over the supported gossip ports. Encrypt production cluster traffic with mutual TLS because gossip is unencrypted by default.
- Design receivers and incident deduplication for at-least-once delivery. Alertmanager deliberately fails open during split brain and may send duplicates rather than miss a critical page.
- Persist and back up the silence and notification-log data needed by the operating policy. Remember that active alerts themselves are not persisted; Prometheus refreshes them.
- Monitor peer count, gossip propagation, notification errors, nflog health, and configuration drift per instance.

## Verification

Send the same alert to all peers, stop one peer, partition the cluster, restart from disk, lose one data directory, and heal the partition. Assert alert delivery continues, duplicates remain acceptable and deduplicated downstream, silences converge, and no instance runs a divergent route.

## Gotchas

- HA prioritizes delivery over exactly-once semantics.
- A healthy UI on one peer does not prove every sender reaches every peer.
- Cross-zone networking policy, MTU, clock, and TLS failures can look like an application-level notification problem.

## Official source

- [Prometheus Alertmanager high availability](https://prometheus.io/docs/alerting/latest/high_availability/)
