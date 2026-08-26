# GitHub Actions cache safety for self-hosted runners

**Issue:** Dependency caching can speed self-hosted runners, but broad keys, sensitive paths, or trust-boundary mistakes can enable stale results, secret exposure, or cache poisoning.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use caches only for reproducible inputs that a job can regenerate after a miss. Build exact cache keys from the runner environment, dependency-manager compatibility, and a cryptographic hash of the authoritative lockfile. Use restore-key prefixes narrowly and treat every restored cache as untrusted input.

GitHub scopes cache access by refs and documents that pull-request and default-branch relationships affect which caches can be read. Self-hosted runners still exchange workflow caches with GitHub-owned storage on GitHub.com. Ensure runner networking can reach the cache service and measure whether remote transfer actually improves duration.

## Operational controls

- Never cache credentials, tokens, signing material, environment files, or authenticated package-manager configuration.
- Do not use cache restoration as proof that dependencies or build outputs are trustworthy.
- Separate cache identities across operating systems, architectures, toolchain versions, and incompatible build flags.
- Pin the cache action to a reviewed immutable commit according to the repository's action-pinning policy.
- Make a miss safe: the workflow must download, verify, and rebuild successfully.
- Track hit rate, restore/save duration, transferred bytes, and end-to-end job time.

## Verification

1. Run the workflow with a cold cache and a warm cache and compare outputs and duration.
2. Change the lockfile and verify an exact cache miss.
3. Exercise a low-trust pull-request path and confirm it cannot mutate protected cache state.
4. Inspect cached paths for sensitive or host-specific files.
5. Simulate cache-service failure and confirm checks still run correctly.

## Sources

- [GitHub Docs: Dependency caching](https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching)
- [GitHub Docs: Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [GitHub Docs: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
