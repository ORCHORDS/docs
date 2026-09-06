---
title: Falco Version Governance (CNCF Falco Runtime Security)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Falco project (https://falco.org/), CNCF graduated; Falco 0.41.x (May 2025), 0.42.x (August 2025), 0.43.x (December 2025), 0.44.x (February 2026), 0.45.x (May 2026), 0.46.x (August 2026); libs (libscap, libdriver); drivers (kernel module, eBPF probe, modern eBPF probe, gVisor, ptrace user space); ruleset repository; CNCF TOC graduation (January 2025)
---

# Falco Version Governance (CNCF Falco Runtime Security)

## Scope

This card governs how `orchords-docs` evaluates Falco and the surrounding ecosystem (Falco ruleset, Falcosidekick, falcoctl, Falco Talon, Falco + Kubernetes response engine). It is the reference input for any KB card that cites runtime detection, syscall capture, eBPF probe, container drift detection, or Kubernetes security response.

## Why this card exists

Falco graduated from CNCF in January 2025 and is the de-facto runtime detection engine for containers and Kubernetes. It is consumed via three deployment shapes (standalone daemonset, Falco + Kubernetes response engine via falco-talon or Falco Kubernetes Audit integration, and managed-by-sidecar). A KB card that cites "Falco" without binding to the supported drivers, ruleset version, and the operator/CRD releases produces an installation that drifts the moment rulesets, drivers, or kubernetes-audit integrations change.

## Version support matrix (2026-09)

| Falco | Released | EoL | Notes |
|---|---|---|---|
| 0.43.x | December 2025 | ~6 months after next minor | stable, eBPF driver |
| 0.44.x | February 2026 | ~6 months after next minor | stable, gVisor integration |
| 0.45.x | May 2026 | ~6 months after next minor | stable, libsinc++ |
| 0.46.x | August 2026 | current | stable, latest rule set |

Policy:

- Support the current minor and the previous minor (N-1).
- Drivers (kernel module, eBPF probe, modern eBPF probe, gVisor, ptrace user space) follow the Falco release they ship in.
- The Falco ruleset repository pins a rules-version tag per Falco minor.
- Upgrade window: ≤ 3 months after a new minor release.

## Driver selection guidance

- Default to the modern eBPF probe for kernels ≥ 5.8 with BTF enabled.
- Fall back to the kernel module only when running on kernels without BTF or with restricted eBPF.
- Avoid the ptrace user-space driver in production; reserve for air-gapped debugging.
- When deploying Falco inside Kubernetes, prefer the Falco daemonset and pin the Falco image tag to a stable minor.

## Ruleset and rule-update cadence

- Pin the ruleset to a SHA tag, not a mutable branch.
- Run `falcoctl` to update rules in CI, not at runtime, unless the runtime supports out-of-band rules update with audit.
- Treat custom rules as code; review and test them like any other detection rule.

## Compatibility notes

- Falcosidekick and Falco Talon follow Falco minor releases within ±1 minor.
- The Falco Kubernetes Audit integration requires Kubernetes API server audit log forwarding and an admission webhook configuration that matches the audit policy.
- When integrating with a SIEM, prefer the Falcosidekick output format that matches the SIEM ingest schema.

References: `https://falco.org/`, `https://github.com/falcosecurity/falco`, `https://github.com/falcosecurity/rules`, `https://github.com/falcosecurity/falcosidekick`, `https://github.com/falcosecurity/falco-talon`, `https://github.com/falcosecurity/falcoctl`.
