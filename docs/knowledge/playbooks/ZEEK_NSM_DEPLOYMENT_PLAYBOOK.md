# Zeek Network Security Monitor Deployment Playbook

## Purpose
Deploy Zeek as a network security monitor in cluster mode with custom scripts, intel framework ingestion from MISP, and integration with SIEM/SOAR. This runbook captures the end-to-end procedure used by the platform team to stand up a production Zeek cluster, validate detection coverage, and hand it to SOC operations. It covers role configuration, Spicy parser tuning, intel feed ingestion, log forwarding, health monitoring, and rollback.

## Audience
Network engineers, SOC analysts, detection engineers, platform engineers. Readers are expected to be familiar with Linux system administration, basic packet analysis, and log forwarding pipelines.

## Pre-conditions
- Monitoring port or network TAP configured on the network segment of interest, with SPAN or mirror session validated end-to-end.
- Dedicated hardware or VM with sufficient RAM (8 GB+ per worker, 16 GB+ recommended for the manager) and SSD-backed storage for the logger.
- Zeek LTS release installed from the official package repository, pinned to a known version.
- MISP intel feed API access and an API key with read permission, plus an allow-listed source IP.
- SIEM ingest endpoint reachable from the logger node, with index naming and field mapping agreed.
- Version-controlled script repository (Git) for custom .zeek files and config.

## Procedure
1. Install the Zeek LTS release on each cluster node using the OS package manager; pin the version and verify checksums against the published manifest.
2. Configure the manager, logger, proxy, and worker roles in node.cfg; assign dedicated IPs and a shared secret for cluster communication.
3. Connect cluster nodes via native Zeek comm (or Broker/ZeroMQ for legacy environments); verify connectivity with `zeekctl status`.
4. Configure the Spicy protocol parser framework and load only the analyzers required for observed traffic to control CPU cost.
5. Tune the logging volume with log rotation, filters, and reducer scripts to keep disk and SIEM ingest within quota.
6. Load MISP indicators into the intel framework via the misp-intel package; schedule daily refresh and verify hits in intel.log.
7. Configure the notice framework thresholds in notice.policy; suppress duplicates and elevate actionable categories.
8. Wire Zeek logs to the SIEM via Filebeat or an output plugin; map conn, http, dns, notice, and intel logs to the correct SIEM index.
9. Define custom scripts in .zeek for organisation-specific detection; lint with `zkg` and stage changes through the Git repo.
10. Set up health monitoring and metrics emission to Prometheus; alert on worker drop, queue depth, and disk usage.
11. Validate detection coverage with an atomic red team exercise; confirm expected notices and intel hits appear in the SIEM.
12. Hand over to SOC operations with a runbook, on-call contacts, and a content-tuning backlog.

## Rollback
Stop the Zeek cluster with `zeekctl stop`, drain in-flight logs from the logger to the SIEM, retain historical logs on cold storage for forensics, and document the rollback window, the reason, and the verification steps performed before returning to a known-good baseline. Notify SOC and the on-call platform engineer before initiating rollback; confirm that no live investigation depends on the node being stopped.

## References
- Zeek governance and cluster architecture: https://docs.zeek.org/en/master/cluster/index.html
- MISP intel framework integration: https://docs.zeek.org/en/master/frameworks/intel.html
- SIEM/SOAR integration cards: see the SIEM integration playbook at `docs/knowledge/playbooks/SIEM_INTEGRATION_PLAYBOOK.md:1`
