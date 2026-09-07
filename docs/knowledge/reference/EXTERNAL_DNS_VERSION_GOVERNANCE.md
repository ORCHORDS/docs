---
title: ExternalDNS Kubernetes DNS Sync Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: ExternalDNS project (kubernetes-sigs/external-dns); Kubernetes SIG; documentation at kubernetes-sigs.github.io/external-dns
---

# ExternalDNS Kubernetes DNS Sync Version Governance

## Overview

This card governs ExternalDNS, the `kubernetes-sigs/external-dns` project that synchronizes Kubernetes `Ingress`, `Service`, and `HTTPRoute` resources with external DNS providers. It is the reference for any KB card that touches public DNS automation, multi-cloud naming, or RFC2136 dynamic update integration with on-prem BIND.

## Provider ecosystem (Route53 / CloudDNS / Azure DNS / Cloudflare / NS1 / PowerDNS / RFC2136)

- Amazon Route53: stable; supports alias records for AWS LBs and ELBv2 via `--aws-zone-type=public|private`. IAM permissions are scoped with a least-privilege policy bound via IRSA.
- Google Cloud DNS: stable; managed zones are auto-discovered when `--gcp-project` is set; record sets support `RRDATA` for DNS-record-type plural records.
- Azure DNS: stable; uses a federated workload identity or AAD pod identity; supports private and public zones.
- Cloudflare: stable; requires an API token with `Zone.DNS:Edit` scope per zone; CNAME flattening is performed by the provider, not ExternalDNS.
- NS1: stable; uses an API key bound to a specific zone; A/PTR records are the only record types in scope.
- PowerDNS: stable; supports the PowerDNS Authoritative Server API; auto-discovery uses `--pdns-server`.
- RFC2136: dynamic update via TSIG-signed messages to a local BIND/PowerDNS-compatible nameserver; use only when the on-prem nameserver is reachable from the cluster and supports TSIG key rotation.

## Registry modes (txt / noop / aws-pgsql)

- `txt`: the default; ExternalDNS writes a TXT record at `<record-prefix>.owner.<zone>` to track ownership and avoid duplicate records. Prefix defaults to `txt-` and can be overridden with `--txt-prefix`.
- `noop`: in-memory only; the provider updates the local model and logs the desired state without calling the registry. Used for dry-run validation and CI gating.
- `aws-pgsql`: PostgreSQL-backed registry that stores ownership in an external RDS instance; mandatory for multi-account Route53 setups where ownership must survive the controller pod losing state.
- Switch between modes by changing the `--registry` flag; never mix `txt` and `aws-pgsql` against the same zone, as the ownership-claim race causes record churn.

## Source/annotation model

- Default source is `service`; add `ingress` and `gateway-httproute` to extend coverage to those resource types.
- Hostnames come from `spec.ports[].name` and `service.beta.kubernetes.io/aws-load-balancer-hostname` annotations on `Service`, and from `spec.rules[].host` on `Ingress`.
- Override targets with the `external-dns.alpha.kubernetes.io/target` annotation; override TTL with `external-dns.alpha.kubernetes.io/ttl`.
- Use `external-dns.alpha.kubernetes.io/alias` for Route53 alias records; the value must be a valid AWS ARN (e.g., `dualstack` ALB).
- Apply `external-dns.alpha.kubernetes.io/hostname` to `Ingress` for routing multiple hostnames to a single backend; this annotation wins over `spec.rules[].host`.

## Domain filters

- `domain-filter=example.com,example.org` scopes reconciliation to the listed zones; this is the single most important safety guardrail for multi-tenant clusters.
- Use `exclude` annotations (`external-dns.alpha.kubernetes.io/exclude`) per-resource to keep a hostname from being created.
- Negative filters are evaluated after positive ones; `regex-domain-filter` supports a Go-regex syntax (e.g., `^.*\.internal\.example\.com$`).
- Always pair `domain-filter` with `--zone-id-filter` for cloud providers that expose zone IDs, otherwise ownership-claim races occur on shared parent zones.

## FQDN templates

- `fqdn-template={{.Name}}.svc.example.com` rewrites every `Service` of `type=LoadBalancer` to a deterministic FQDN; useful for service-mesh and shared-zone topologies.
- The template engine operates on the upstream object's `Name` and `Namespace`; use `{{.Name}}.{{.Namespace}}.example.com` for namespaced routing.
- Avoid templates that depend on `metadata.labels` unless the labels are enforced by an admission controller; otherwise FQDN drift becomes hard to debug.
- Templates are applied per-provider; the same `Service` can produce different FQDNs across providers if `--provider` is reconfigured.

## Registry ownership TTL

- The TXT ownership record has its own TTL, set independently from the A/AAAA record TTL via the `txt-ttl` flag (default 600s).
- For dynamic environments, keep `txt-ttl` between 30s and 600s so deleted records propagate quickly; for static zones, align `txt-ttl` with the zone SOA minimum.
- Ownership records are scoped per-provider and per-zone; rotating the `txt-prefix` triggers a re-claim cycle and should be done in a planned change window.

## Pod disruption budget and HA

- Run ExternalDNS as a `Deployment` with at least two replicas; leader election is implicit (single-writer) when the registry is `txt` or `aws-pgsql`.
- For `noop` registry mode, all replicas process records in parallel; do not scale past 3 replicas without enabling `--events` throttling.
- Pin `minAvailable: 1` in a `PodDisruptionBudget` so node drains do not drop DNS updates.
- Keep the controller's `--interval` at 1m or longer to avoid hammering provider APIs; for high-churn environments, shorten the interval but bound it with `--events` log lines.

## Upgrade path with provider migrations

- Pin a chart version (`external-dns/external-dns: 1.x.y`); upgrade within the same minor before crossing a major.
- When migrating providers (e.g., Route53 → CloudDNS), deploy a second ExternalDNS instance with `--provider=google` and a unique `txt-prefix`; let the new instance take over the zone before removing the old one.
- Drop deprecated `--provider=aws` flags in favor of `--provider=aws` with `--aws-zone-type=public` after the 0.13 line; provider-specific flags changed shape during the 1.x line.
- Always run `--registry=noop --txt-prefix=verify` first when introducing a new annotation; promote the registry only after dry-run output is reviewed.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07. The card is re-evaluated on every upstream minor release, on provider API changes (Route53, Cloud DNS, Cloudflare), and on any cluster migration between cloud providers.

## References

- Upstream repository: `https://github.com/kubernetes-sigs/external-dns`
- Documentation: `https://kubernetes-sigs.github.io/external-dns/`
- Releases and changelog: `https://github.com/kubernetes-sigs/external-dns/releases`
- Provider matrix: `https://kubernetes-sigs.github.io/external-dns/#providers-and-capabilities`
- Helm chart: `https://github.com/kubernetes-sigs/external-dns/tree/master/charts/external-dns`
- Gateway API source: `https://gateway-api.sigs.k8s.io/`
