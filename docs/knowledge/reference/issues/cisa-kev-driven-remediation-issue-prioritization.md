# CISA KEV-driven remediation issue prioritization

**Issue:** Vulnerability backlogs ranked only by CVSS can leave actively exploited vulnerabilities behind higher-scoring theoretical findings.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Ingest CISA's Known Exploited Vulnerabilities catalog as an active-exploitation signal and automatically raise a remediation issue when an inventory match is confirmed. Do not create noisy tickets from CVE string matches without verifying affected product, version, and deployment.

BOD 22-01 due dates bind US federal civilian executive branch agencies. Other organizations may use them as a strong prioritization input but must not misstate their legal applicability.

## Issue contract

Each confirmed issue records the CVE, catalog date, CISA due date, affected component and version, deployed locations, owner, exposure, mitigation, fixed version, rollout plan, and verification evidence. Link inventory evidence without exposing internal topology publicly.

## Flow

1. Fetch the signed/HTTPS catalog on a schedule and detect additions or material field changes.
2. Join by normalized identifiers, then validate package identity and affected ranges.
3. Open or update one canonical issue per vulnerability and affected service group.
4. Page the security owner for internet-exposed or critical matches.
5. Prefer vendor remediation; document isolation or disablement when no patch exists.
6. Track merge, artifact rebuild, deployment, and rescan as separate milestones.
7. Close only when deployment inventory and the original detector confirm removal.

## Verification

Use fixture catalog changes to test ingestion, deduplication, ownership, SLA calculation, reopening, and false-positive suppression. Audit that issue state matches current catalog and inventory.

## Gotchas

Catalog removal or correction requires reconciliation. KEV absence does not mean safe. CVE aliases, vendored code, and stale inventories cause missed or false matches.

## Sources

- [CISA Known Exploited Vulnerabilities Catalog](https://www.cisa.gov/known-exploited-vulnerabilities-catalog)
- [CISA KEV prioritization and BOD 22-01 scope](https://www.cisa.gov/news-events/alerts/2025/03/31/cisa-adds-one-known-exploited-vulnerability-catalog)
