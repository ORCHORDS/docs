# D1 creation-time data location contract

**Issue:** A D1 location hint is treated as a residency guarantee, or a jurisdiction is added after creation even though the database placement contract is fixed at creation time.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Decide jurisdiction and primary-location intent before creating each production database.
- Use `--jurisdiction=eu` or `--jurisdiction=fedramp` only for the supported hard residency constraint; record it in IaC and the data inventory.
- Treat `--location` as a latency hint, not a guarantee. If both are supplied, jurisdiction takes precedence.
- Migrate into a newly created database when the required jurisdiction changes; do not assume an in-place update exists.
- Remember that jurisdiction constrains where D1 runs and persists data, not where requests may originate. Use Regional Services or another ingress control when response location also matters.
- Verify read replicas remain inside the configured jurisdiction.

## Verification

Inspect the created database through the API, test IaC drift, rehearse export/import migration, and measure writes from the real writer region rather than the operator's laptop or CI location.

## Gotchas

Automatic placement is based near the creation request. A CI system in the wrong region can therefore choose an undesirable primary unless the creation contract is explicit.

## Official sources

- [Cloudflare D1 data location](https://developers.cloudflare.com/d1/configuration/data-location/)
