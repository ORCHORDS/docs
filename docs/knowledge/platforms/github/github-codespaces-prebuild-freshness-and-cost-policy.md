# Govern Codespaces Prebuild Freshness and Cost

**Issue:** Prebuilds reduce startup work but can become stale, fail silently into non-prebuilt creation, multiply regional storage cost, and require broader build-time permissions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Scope each configuration to an explicit branch, devcontainer file, trigger, regions, and retained-version count.
- Choose every-push, configuration-change, or scheduled updates from measured freshness needs.
- Put reusable setup in the documented prebuild commands and keep user-specific secrets out of prebuild assumptions.
- Minimize repository permissions and authorize cross-repository access deliberately.
- Notify an owning team on workflow failure and monitor availability/fallback.
- Review Actions minutes, storage by region/version, and startup benefit together.

## Verification
- Change dependencies and devcontainer configuration and assert the selected trigger refreshes the image.
- Force a failed prebuild and verify the chosen optimized/fallback behavior.
- Create from supported and unsupported branches, regions, and machine types.
- Audit the snapshot for secrets and stale generated artifacts.

## Gotchas
Prebuild creation uses GitHub Actions and billable storage. User secrets are unavailable during build; repository or organization Codespaces secrets may have broad consequences.

## Official sources
- [GitHub: Configuring prebuilds](https://docs.github.com/en/codespaces/prebuilding-your-codespaces/configuring-prebuilds)
- [GitHub: About Codespaces prebuilds](https://docs.github.com/en/codespaces/prebuilding-your-codespaces/about-github-codespaces-prebuilds)
