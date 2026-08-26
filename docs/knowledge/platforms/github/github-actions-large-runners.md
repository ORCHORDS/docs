# github-actions-large-runners

**Issue:** Using GitHub-hosted larger runners for CPU/memory-intensive workloads
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Standard runners (2 vCPU, 7 GB RAM) are insufficient for Docker builds, Rust compilation, or ML model training. Larger runners offer up to 64 vCPU.

## Pattern / Solution
```yaml
jobs:
  heavy-build:
    runs-on: ubuntu-latest-16-core
    steps:
      - uses: actions/checkout@v4
      - run: cargo build --release

  docker-build:
    runs-on: ubuntu-latest-8-core
    steps:
      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64,linux/arm64
```
Available GitHub-hosted runner labels:
- `ubuntu-latest-4-core` / `ubuntu-latest-8-core` / `ubuntu-latest-16-core` / `ubuntu-latest-64-core`
- `windows-latest-8-core` / `macos-latest-xlarge`

## Gotchas
- Larger runners cost more per minute — check pricing before defaulting to them.
- They are only available on GitHub Team and Enterprise plans.
- Runner groups must be configured at the org level to grant repo access.
- Not all regions have all runner sizes — check GitHub's availability matrix.
- For ARM workloads, use `macos-latest-xlarge` (Apple Silicon) or the `arm` Ubuntu variants.

## Related
- `github-actions-self-hosted-runners-2026.md`
- `github-actions-gpu-runners.md`
