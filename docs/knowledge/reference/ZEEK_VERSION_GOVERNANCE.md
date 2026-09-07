---
title: "Zeek Network Security Monitor Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "Zeek project (formerly Bro) release notes and Corelight deployment guidance"
---

# Zeek Network Security Monitor Version Governance

## Overview

Zeek is an open-source network security monitor historically distributed as "Bro." It passively inspects traffic, generates structured logs, and emits policy-level notices suitable for downstream SIEM ingestion. Governance of the platform spans language policy, script bundle selection, cluster topology, and parser framework alignment.

## Scripting Language

Zeek scripts use the `.zeek` extension and execute against an event-driven runtime. Policy authors subscribe to engine events such as `connection_established`, `http_request`, and `dns_query`. Scripts are loaded declaratively with `@load` directives, allowing layered composition across protocols, frameworks, and policy packages.

## Default Script Layout

The canonical script tree organizes the default bundle as follows:

- `base/protocols/*` - protocol analyzers including HTTP, DNS, SSL, SMTP, and SSH
- `base/frameworks/*` - reusable subsystems (intel, notice, input, logging, cluster)
- `base/policy/*` - tunable policy bundles (tuning, misc, securityonion)

Operators may layer site-local scripts in `site/` and load them via `@load_site`.

## Log Writers

Default ASCII writers emit one file per stream:

- `conn.log` - connection summaries
- `http.log` - HTTP transactions
- `dns.log` - DNS messages
- `ssl.log` and `x509.log` - TLS metadata and certificate chain records
- `files.log` - file analysis results
- `notice.log` - policy alerts

JSON or CSV writers replace the default ASCII stream where required.

## Cluster Topology

Zeek clusters assign nodes to four roles: manager, logger, proxy, and worker. The manager coordinates configuration; the logger persists all log streams; proxies distribute traffic across workers using a hash policy; workers run analyzers and forward events. Single-host deployments collapse these roles onto one node.

## Cluster Communication

Legacy clusters communicate over Broker, a ZeroMQ-based messaging layer. Newer releases replace Broker with native Zeek communication (ZAM), reducing external dependencies and improving throughput.

## Parser Framework

Spicy is the current protocol parser framework, replacing the legacy binpac generator. Spicy parsers are type-safe, easier to maintain, and integrate with Zeek events at the analyzer boundary.

## Core Frameworks

Key frameworks shape detection and data ingestion:

- intel framework - matches observables against threat intelligence feeds
- notice framework - produces categorized alerts
- file analysis - extracts and evaluates transferred files
- input framework - streams external data into the event engine

## Compatibility Horizon

Zeek publishes LTS releases roughly every 12 months. LTS branches receive security and stability fixes for an extended window. Feature releases track trunk. Plan upgrades against the EOL matrix.

## Version Selection Decision Tree

1. Single-node sensor - latest LTS.
2. Multi-node cluster - latest LTS confirmed across proxy and worker.
3. Custom Spicy parsers - feature branch pinned to an LTS base.
4. Policy bundle selection - choose `base/policy/tuning` plus site overlays.

## Operational Impact Points

- Memory budget per worker scales with the active script set.
- Log retention is governed by logger disk and rotation policy.
- Tuning proceeds through `policy/tuning`, then site overlays, then framework knobs.

## Cross-References

See protocol log schema details at `docs/knowledge/reference/ZEEK_LOG_SCHEMA.md:1`, parser migration guidance at `docs/knowledge/reference/SPICY_PARSER_MIGRATION.md:1`, and cluster sizing references at `docs/knowledge/reference/ZEEK_CLUSTER_SIZING.md:1`.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.