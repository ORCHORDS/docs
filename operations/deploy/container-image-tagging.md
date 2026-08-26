# container-image-tagging

**Issue:** Docker and OCI image tagging conventions that make deploys deterministic and rollbacks trivial
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Mutable tags like `latest` or `main` are the most common cause of "it worked yesterday" deploy failures. Immutable, content-addressed tagging eliminates this class of problem entirely.

## Pattern / Solution
**Tag anatomy**
```
ghcr.io/<org>/<image>:<tag>@sha256:<digest>

Examples:
ghcr.io/acme/api:v2.41.3
ghcr.io/acme/api:sha-a3f8c21
ghcr.io/acme/api:v2.41.3@sha256:abc123...  ← most secure: immutable by digest
```

**Tagging matrix**
| Trigger | Tags applied |
|---|---|
| Merge to main | `sha-<short>`, `main` |
| Semver tag push (`v*.*.*`) | `v2.41.3`, `v2.41`, `v2`, `latest` |
| Pull request | `pr-<number>` |

**Kubernetes: always pin by digest in production**
```yaml
# Instead of:
image: ghcr.io/acme/api:v2.41.3

# Use digest for immutability:
image: ghcr.io/acme/api:v2.41.3@sha256:abc123def456...
```

**Automated digest pinning with Renovate**
```json
// renovate.json
{
  "docker": {
    "pinDigests": true
  }
}
```

**Tag cleanup policy (GitHub Container Registry)**
```bash
# Delete untagged images older than 30 days using ghcr-cleanup-action in CI
- uses: snok/container-retention-policy@v2
  with:
    image-names: api
    cut-off: 30 days ago UTC
    keep-at-least: 5
    filter-tags: sha-*
    token: ${{ secrets.GITHUB_TOKEN }}
```

## Gotchas
- `latest` is pushed by default by many build tools unless explicitly disabled — always check
- Multi-arch images have a single manifest list tag but multiple platform-specific digests; pin the manifest list digest
- Image digests change on every rebuild even if the source is identical (due to timestamps in layers) — use reproducible builds or `--no-cache` consistently
- Registry mirrors used in CI should also enforce digest pinning

## Related
- `artifact-versioning-strategy.md`
- `docker-multi-stage-build.md`
- `docker-layer-caching-ci.md`
- `kubernetes-rolling-update.md`
