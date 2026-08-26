# pnpm Minimum Release Age as a Supply-Chain Delay

**Issue:** Immediately resolving a newly published package version gives defenders little time to detect a compromised or mistakenly published release.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Control pattern

Configure `minimumReleaseAge` in the repository's `pnpm-workspace.yaml` so versions younger than the chosen number of minutes are excluded from resolution. Select the delay from the organization's patch urgency and threat model rather than copying an arbitrary value.

Use the related exclusion setting only for narrowly documented emergency dependencies. Review exclusions like privileged exceptions, with an owner and expiry. Current pnpm also documents strict and missing-time behavior; decide explicitly how packages without reliable publication timestamps and dependency trees should be handled.

Keep the lockfile committed and use frozen installs in CI. The age gate limits new resolution; it does not retroactively make an already locked malicious version safe and does not replace provenance, review, or vulnerability scanning.

## Rollout

1. Pin the pnpm version through the repository's package-manager declaration and CI setup.
2. Add the policy in one change with no unrelated dependency upgrades.
3. Regenerate the lockfile in a trusted environment.
4. Test clean install, offline/limited-network behavior, workspace filtering, and emergency patch workflow.
5. Record resolution failures caused by age policy separately from registry outages.
6. Require review for exclusions and periodically remove stale ones.

## Verification

Create an internal test package or controlled fixture with a recent publish timestamp and prove it is rejected while an older permitted version resolves. Confirm `pnpm install --frozen-lockfile` still reproduces the approved graph. Exercise the documented emergency override without weakening the default policy.

## Gotchas

Registry timestamp availability and mirrors can affect decisions. Broad wildcard exclusions defeat the delay. A delay can postpone urgent fixes, so maintain a reviewed break-glass path that still runs the complete test and security checks.

## Sources

- [pnpm settings reference](https://pnpm.io/settings)
- [pnpm supply-chain mitigation guidance](https://pnpm.io/supply-chain-security)
- [pnpm continuous-integration guidance](https://pnpm.io/continuous-integration)
