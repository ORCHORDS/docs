# GitHub Dependabot inactivity deactivation monitoring

**Issue:** Dependency updates silently pause after maintainers stop interacting with Dependabot pull requests.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Assign update owners; monitor Dependabot status and last generated/merged/closed PR; define interaction expectations; alert on automatic deactivation; separate security-update coverage from version-update hygiene; periodically verify configuration, registries, directories, and schedules.

## Verification

Use a canary dependency, confirm scheduled PR generation and security-alert remediation, detect paused state, reactivate through documented workflow, and verify notifications reach active maintainers.

## Gotchas

No PR can mean up-to-date, misconfigured, rate-limited, or deactivated. Grouping may hide individual ownership. Closing PRs without rationale is not healthy interaction.

## Sources

- [GitHub Docs: Dependabot security updates and automatic deactivation](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-security-updates)
