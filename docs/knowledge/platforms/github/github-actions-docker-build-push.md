# github-actions-docker-build-push

**Issue:** Building and pushing Docker images from GitHub Actions with layer caching
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Docker builds in CI are slow without layer caching, and pushing to multiple registries requires boilerplate auth steps. Teams need a reliable, fast pattern using the official Docker actions.

## Pattern / Solution
Use `docker/setup-buildx-action`, `docker/login-action`, and `docker/build-push-action` together. Buildx is required for cache export/import.

**Full build-push workflow with GitHub Container Registry:**
```yaml
name: Docker

on:
  push:
    branches: [main]
  pull_request:

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write         # required for ghcr.io push

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        if: github.event_name != 'pull_request'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker meta
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha
            type=ref,event=branch
            type=semver,pattern={{version}}

      - uses: docker/build-push-action@v6
        with:
          context: .
          push: ${{ github.event_name != 'pull_request' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          platforms: linux/amd64,linux/arm64
```

**Multi-registry push (GHCR + Docker Hub):**
```yaml
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```

## Gotchas
- `cache-from: type=gha` requires Buildx and the GitHub Actions cache backend — don't mix with inline cache (`type=inline`) as they conflict
- `platforms: linux/amd64,linux/arm64` cross-compilation is slow; consider separate jobs per platform with `docker/bake-action` for large images
- The `GITHUB_TOKEN` has `packages: write` permission only if explicitly granted in the workflow `permissions:` block
- `metadata-action` semver tags only trigger when the push is a tag matching `v*.*.*` — test with `git tag v1.0.0 && git push --tags`
- Buildx builders don't persist between jobs — each job must call `setup-buildx-action` again

## Related
- `github-actions-oidc-cloudflare.md`
- `github-actions-secrets-management.md`
- `github-packages-npm-registry.md`
