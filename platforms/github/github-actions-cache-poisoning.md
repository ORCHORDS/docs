# GitHub Actions cache poisoning risk

**Date:** 2026-08-26
**Status:** documented
**Sources:**
- https://docs.github.com/en/actions/concepts/workflows-and-actions/dependency-caching
- https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching

## Context

GitHub documents that Actions cache contents are not signed or verified. A workflow that can read a cache restores its contents as-is, and malicious cache contents can influence files that are later executed.

## Security pattern

- Treat restored cache data as untrusted input.
- Never cache secrets, credentials, tokens, private keys, or sensitive configuration.
- Restrict cache writes to trusted triggers and hardened workflows.
- Ensure builds can re-download or regenerate dependencies when a cache is unavailable.
- Keep cache keys scoped enough to avoid accidental cross-context reuse.
- Do not use a cache as an artifact-integrity mechanism.

## Pull-request boundary

GitHub warns that users able to open pull requests can potentially read base-branch cache contents. Design cached paths on the assumption that they may become observable to lower-trust workflows.

## Verification

1. Inspect every cached path for secret-bearing files.
2. Identify which events can write each cache.
3. Run a build with cache disabled/missed to prove reproducibility.
4. Confirm untrusted PR workflows cannot introduce executable cache state later consumed by a privileged workflow.

## Related

- `github-actions-security.md`
- `github-actions-cache.md`
