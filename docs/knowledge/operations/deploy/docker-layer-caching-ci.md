# docker-layer-caching-ci

**Issue:** Speeding up Docker builds in CI by correctly configuring layer cache reuse
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CI Docker builds run from scratch every time, taking 5–15 minutes, because the cache is not persisted between runs. Proper cache configuration reduces build times to under a minute for unchanged dependency layers.

## Pattern / Solution
**GitHub Actions with registry cache (recommended)**
```yaml
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3

- name: Log in to registry
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}

- name: Build and push
  uses: docker/build-push-action@v5
  with:
    context: .
    push: true
    tags: ghcr.io/org/api:sha-${{ github.sha }}
    cache-from: type=registry,ref=ghcr.io/org/api:buildcache
    cache-to: type=registry,ref=ghcr.io/org/api:buildcache,mode=max
```

**GitHub Actions with gha cache (simpler, no registry needed)**
```yaml
- name: Build and push
  uses: docker/build-push-action@v5
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Dockerfile layer order for maximum cache hits**
```dockerfile
# GOOD — dependency install cached until package.json changes
COPY package*.json ./
RUN npm ci
COPY . .          ← source copy comes last
RUN npm run build

# BAD — COPY . . invalidates the npm ci cache on every source change
COPY . .
RUN npm ci
RUN npm run build
```

**Cache invalidation control**
```dockerfile
# Force-bust a specific layer without changing source
ARG CACHE_BUST=1
RUN --mount=type=cache,target=/root/.npm npm ci
```

## Gotchas
- `mode=max` caches all intermediate layers; `mode=min` only caches the final image layers — use `max` for build speed
- The GHA cache has a 10 GB limit per repo; large monorepos may evict each other's caches
- Registry cache (`type=registry`) works across runners and is not subject to the GHA cache size limit
- Multi-platform builds (buildx `--platform linux/amd64,linux/arm64`) cache separately per platform

## Related
- `docker-multi-stage-build.md`
- `container-image-tagging.md`
