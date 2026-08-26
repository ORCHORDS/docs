# Dependency Default Change Needs an Upgrade-Path Test

**Issue:** A dependency upgrade can keep its API while changing a default for timeouts, parsing, encryption, retries, or resource limits. Clean-install tests miss the risk to existing deployments.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Diff effective configuration and release notes across the old and new dependency versions.
- Pin security- or reliability-critical behavior explicitly instead of inheriting a changing default.
- Test both a fresh installation and an upgrade using representative persisted configuration and data.
- Record the old default, new default, chosen policy, and rollback behavior in the upgrade decision.

## Verification

- Start from the previous production version and perform the real upgrade sequence.
- Omit the affected setting and assert the effective value before and after upgrade.
- Exercise rollback after the new version has written state or configuration.

## Gotchas

- Generated configuration files may freeze an old default while new installations inherit the new one.
- A backward-compatible schema does not guarantee backward-compatible runtime behavior.

## Official sources

- https://sre.google/sre-book/release-engineering/
- https://sre.google/workbook/configuration-design/
