# GitHub Dependabot cooldown security boundary

**Issue:** Teams use update cooldowns to reduce version churn and accidentally assume security updates are delayed the same way.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use Dependabot `cooldown` only for version-update stability policy. GitHub documents that cooldown does not apply to security updates and that the default three-day version cooldown does not delay security updates.

## Controls

Define ecosystem-specific major/minor/patch windows; exclude urgent or fast-moving packages; keep security updates enabled; group only updates that share testing/ownership; document PR limits and schedule; monitor paused/deactivated updates.

## Verification

In a test repository, simulate a normal release and a security advisory and confirm different timing. Validate generated PR grouping and ensure CI exercises the full dependency set.

## Gotchas

Grouping increases blast radius. Compatibility scores are signals from other public CI, not proof for this repository. Cooldown is not a vulnerability SLA.

## Sources

- [GitHub Docs: Optimizing Dependabot version-update PRs](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/optimizing-pr-creation-version-updates)
- [GitHub Docs: Dependabot security updates](https://docs.github.com/en/code-security/concepts/supply-chain-security/dependabot-security-updates)
