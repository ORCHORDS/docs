# Dependabot Multi-Ecosystem Group Review Boundary

**Issue:** Grouping Docker, Terraform, npm, and other updates can reduce PR volume, but it also creates a larger coupled review and rollback boundary.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Group only dependencies that are operationally released and validated together.
- Define a top-level multi-ecosystem schedule and explicit patterns for each participating ecosystem.
- Apply CODEOWNERS, labels, and test matrices covering every ecosystem changed by the grouped PR.
- Keep security-critical or independently deployed dependencies outside a group when they need separate urgency or rollback.

## Verification

- Validate dependabot.yml and confirm the group appears in repository Dependabot settings.
- Trigger representative updates in two ecosystems and confirm a single PR receives all required checks.
- Revert a grouped update in staging and verify each ecosystem returns to a compatible state.

## Gotchas

- Multi-ecosystem grouping differs from single-ecosystem groups and has different configuration placement.
- Fewer PRs can mean larger review blast radius.

## Official sources

- https://docs.github.com/en/code-security/concepts/supply-chain-security/multi-ecosystem-updates
- https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/secure-your-dependencies/configuring-multi-ecosystem-updates
