---
title: Backstage Version Governance (CNCF Backstage IDP)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Backstage project (https://backstage.io/), CNCF Incubating; Backstage 1.30 (May 2025), 1.31 (July 2025), 1.32 (October 2025), 1.33 (January 2026), 1.34 (April 2026), 1.35 (July 2026), 1.36 (August 2026); plugins (catalog, scaffolder, techdocs, kubernetes, github, gitlab, argocd); TechDocs CLI; Backstage CLI
---

# Backstage Version Governance (CNCF Backstage IDP)

## Scope

This card governs how `orchords-docs` evaluates Backstage and the surrounding ecosystem (Backstage CLI, Backstage plugins catalog, TechDocs, scaffolder, Kubernetes plugin, software templates). It is the reference input for any KB card that cites internal developer portals, software catalogs, golden paths, or TechDocs sites.

## Why this card exists

Backstage was donated to CNCF and is the de-facto open-source internal developer portal (IDP). The project ships a monthly minor release and a curated plugins catalog that is versioned independently of the core. A KB card that cites "Backstage" without binding to the core minor, the plugin set, and the scaffolder / TechDocs compatibility produces an installation that breaks on plugin upgrade.

## Version support matrix (2026-09)

| Backstage | Released | EoL | Notes |
|---|---|---|---|
| 1.33 | January 2026 | ~30 days after 1.34 | supported |
| 1.34 | April 2026 | ~30 days after 1.35 | supported |
| 1.35 | July 2026 | ~30 days after 1.36 | supported |
| 1.36 | August 2026 | current | latest |

Policy:

- Support the current minor and the previous minor (N-1).
- Upgrade window: ≤ 30 days after a new minor release.
- Plugins must be pinned to versions that declare compatibility with the running core minor; otherwise the install fails at startup.

## Plugin compatibility guidance

- Pin every plugin to a version that declares `@backstage/core-plugin-api` compatibility matching the running core.
- Use the Backstage CLI `plugin:diff` workflow to detect breaking changes when bumping core.
- Avoid the legacy frontend system plugin shape for new plugins; prefer the new frontend system shape that shipped in 1.30+.

## Software templates

- Templates are JSON Schema + TypeScript files in the scaffolder backend; pin scaffolder actions to versions that match the running core minor.
- When the scaffolder dry-run produces a different tree than the actual run, escalate; do not silently accept drift.

## TechDocs

- TechDocs is split between a publisher and a reader; pin both to versions that match the core minor.
- Treat TechDocs `mkdocs.yml` overrides as code; review them under change control.

## Identity and integrations

- Pin the identity resolver to the supported provider (GitHub Apps, GitLab, Okta, Google IAP) version that the running core minor supports.
- When integrating with a managed Kubernetes cluster, the Kubernetes plugin must be pinned to a version that matches the running core minor.

References: `https://backstage.io/`, `https://github.com/backstage/backstage`, `https://github.com/backstage/backstage/blob/master/plugins/README.md`, `https://backstage.io/docs/plugins/`.
