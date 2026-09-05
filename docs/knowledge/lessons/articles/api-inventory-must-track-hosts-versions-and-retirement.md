# API Inventory Must Track Hosts, Versions, and Retirement

**Issue:** Teams document current endpoints but cannot answer which API hosts exist, which environment each host belongs to, which version is running, who may reach it, or when an old version should be removed.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP API9:2023 identifies missing host inventory, stale documentation, and absent version-retirement plans as security blind spots. Old or forgotten API deployments remain attack surface even when the main production version is well maintained.

## Engineering rule

- Inventory every API host, not only endpoint definitions in the primary repository.
- Record environment, intended network audience, owner, deployed version, and retirement state.
- Assign a retirement plan to every version that can become obsolete.
- Include beta, staging, test, partner, and legacy hosts in exposure reviews.
- Keep documentation generation tied to delivery pipelines where feasible.

## Verification

- Compare DNS, gateway, cloud, and deployment inventories against the documented API host list.
- Attempt to locate versions not represented in the inventory.
- Confirm each non-current version has an owner, support decision, and retirement or backport plan.

## Official source

- OWASP API9:2023 Improper Inventory Management: https://owasp.org/API-Security/editions/2023/en/0xa9-improper-inventory-management/
