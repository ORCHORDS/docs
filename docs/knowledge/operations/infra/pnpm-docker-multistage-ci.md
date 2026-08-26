# pnpm Workspaces with Docker Multi-Stage Builds for CI

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A pnpm workspace monorepo can have hundreds of packages. A naive `COPY . .` inside a
Dockerfile pulls everything into the image context, causing build times to balloon and
Docker layer cache to bust on every commit regardless of which package changed. The
challenge is threefold: (1) install only the dependencies required by the specific app
being containerised, (2) exploit Docker layer caching aggressively so the expensive
`pnpm install` step is skipped when lockfiles and manifests haven't changed, and (3) do
this reliably in CI where runners may have cold caches.

This article covers the combination of pnpm workspaces and Docker multi-stage builds,
including `pnpm fetch`, `pnpm deploy`, `--mount=type=cache`, and pnpm-aware base images.
It is distinct from the general `docker-multi-stage-build-optimization.md` article
(which is framework-agnostic) and the `pnpm-workspaces-monorepo.md` article (which
covers local development workflow).

## Context

pnpm's virtual store (`node_modules/.pnpm`) keeps all packages as hard links from a
central content-addressable store. This makes pnpm very fast locally but creates a
challenge in Docker: you cannot `COPY node_modules` from a CI host into a container
because the hard links point to a store path that does not exist inside the container.

Two pnpm features designed for container workflows:

- **`pnpm fetch`**: Downloads all packages from the registry into `.pnpm-store` based
  solely on `pnpm-lock.yaml`, without reading any `package.json`. This lets you cache
  the full dependency download before copying any source code.
- **`pnpm deploy`**: Creates a self-contained deployment directory for a single workspace
  package — it copies only the package's production dependencies (resolved from the
  workspace) into a flat `node_modules`, suitable for a minimal runtime image.

## Repository structure assumption

```
repo/
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── package.json          (root, no src)
├── apps/
│   ├── api/
│   │   ├── package.json
│   │   └── src/
│   └── web/
│       ├── package.json
│       └── src/
└── packages/
    ├── shared/
    │   └── package.json
    └── config/
        └── package.json
```

```yaml
# pnpm-workspace.yaml
packages:
  - "apps/*"
  - "packages/*"
```

## Dockerfile — recommended pattern

```dockerfile
# Dockerfile (for apps/api)
# ──────────────────────────────────────────────────────────
# Stage 1: dependency fetcher
# Uses pnpm fetch to cache all registry downloads
# behind the lockfile layer.
# ──────────────────────────────────────────────────────────
FROM node:22-alpine AS deps-fetcher

# Install pnpm via corepack (matches version in package.json#packageManager)
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /repo

# Copy ONLY the lockfile — changes here invalidate the fetch cache
COPY pnpm-lock.yaml ./

# Fetch all packages into .pnpm-store (no node_modules yet)
# This layer is cache-stable as long as pnpm-lock.yaml is unchanged
RUN pnpm fetch --prod

# ──────────────────────────────────────────────────────────
# Stage 2: full installer + builder
# Adds all package.json files and installs from the local store
# ──────────────────────────────────────────────────────────
FROM deps-fetcher AS builder

# Copy manifests for all workspace packages
# (triggers reinstall only when package.json files change)
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/api/package.json    ./apps/api/package.json
COPY apps/web/package.json    ./apps/web/package.json
COPY packages/shared/package.json ./packages/shared/package.json
COPY packages/config/package.json ./packages/config/package.json

# Install from the pre-fetched offline store
RUN pnpm install --offline --frozen-lockfile

# Copy source after dependencies are installed
COPY apps/api   ./apps/api
COPY packages   ./packages

# Build the target app
RUN pnpm --filter api build

# ──────────────────────────────────────────────────────────
# Stage 3: deploy (isolate app + its deps)
# pnpm deploy creates a self-contained directory with
# only production node_modules for apps/api
# ──────────────────────────────────────────────────────────
FROM builder AS deployer

RUN pnpm --filter api deploy --prod /deploy/api

# ──────────────────────────────────────────────────────────
# Stage 4: runtime image (minimal)
# ──────────────────────────────────────────────────────────
FROM node:22-alpine AS runtime

WORKDIR /app

# Copy only the isolated deployment directory
COPY --from=deployer /deploy/api .

EXPOSE 3000
CMD ["node", "dist/main.js"]
```

The final `runtime` stage contains only the `apps/api` output and its production
`node_modules` — no pnpm store, no dev dependencies, no other workspace packages.

## BuildKit cache mounts for the pnpm store

`--mount=type=cache` persists the pnpm store between builds on the same runner host:

```dockerfile
# Alternative Stage 1 using BuildKit cache mount
FROM node:22-alpine AS deps-fetcher
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /repo
COPY pnpm-lock.yaml ./

# Mount the pnpm store cache between builds on the same host
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm fetch --prod
```

Enable BuildKit in CI:

```bash
export DOCKER_BUILDKIT=1
docker build --build-arg BUILDKIT_INLINE_CACHE=1 -t my-api .
```

Or in `docker-compose.yml`:

```yaml
services:
  api:
    build:
      context: .
      cache_from:
        - type=local,src=/tmp/docker-cache
      cache_to:
        - type=local,dest=/tmp/docker-cache,mode=max
```

## GitHub Actions workflow

```yaml
# .github/workflows/build-api.yml
name: Build API

on:
  push:
    paths:
      - "apps/api/**"
      - "packages/**"
      - "pnpm-lock.yaml"
      - "Dockerfile"

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}/api
          tags: |
            type=sha,prefix=sha-
            type=ref,event=branch
            type=semver,pattern={{version}}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          file: ./Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
          # Pass which app to target if using a parameterised Dockerfile
          build-args: |
            APP=api
```

The `cache-from: type=gha` / `cache-to: type=gha,mode=max` combination uses GitHub
Actions' own cache backend (up to 10 GB per repository) and is the most reliable
layer-cache strategy on ephemeral GitHub runners.

## Parameterised Dockerfile for multiple apps

If you have several apps, avoid one Dockerfile per app:

```dockerfile
ARG APP=api
FROM node:22-alpine AS deps-fetcher
RUN corepack enable && corepack prepare pnpm@latest --activate
WORKDIR /repo
COPY pnpm-lock.yaml ./
RUN pnpm fetch --prod

FROM deps-fetcher AS builder
ARG APP
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
# Copy all manifests (cheap COPY, stable layer)
COPY apps/*/package.json ./apps/
COPY packages/*/package.json ./packages/
RUN pnpm install --offline --frozen-lockfile
COPY apps/${APP} ./apps/${APP}
COPY packages    ./packages
RUN pnpm --filter ${APP} build

FROM builder AS deployer
ARG APP
RUN pnpm --filter ${APP} deploy --prod /deploy/${APP}

FROM node:22-alpine AS runtime
ARG APP
WORKDIR /app
COPY --from=deployer /deploy/${APP} .
EXPOSE 3000
CMD ["node", "dist/main.js"]
```

Build with:

```bash
docker build --build-arg APP=web -t my-web .
docker build --build-arg APP=api -t my-api .
```

## `.dockerignore` — critical for context size

```dockerignore
node_modules
.pnpm-store
dist
.next
.turbo
*.log
.env*
.git
coverage
.wrangler
```

Without `.dockerignore`, the pnpm virtual store (`node_modules/.pnpm`) — potentially
gigabytes — gets sent to the Docker daemon context on every build. This alone can add
minutes to CI runs.

## Layer cache hit rates — expected behaviour

| Change made                             | Layers rebuilt         |
|-----------------------------------------|------------------------|
| Source code only (no lockfile change)   | Stage 3 (deploy) only  |
| `package.json` script/version bump      | Stage 2 install onward |
| `pnpm-lock.yaml` updated (new dep)      | Stage 1 fetch onward   |
| Base image (`node:22-alpine`) updated   | All stages             |

Aim for source-only changes to hit 75-80% cache hit rate on a warmed GHA cache.

## Anti-patterns

- `COPY . .` as the first step — busts cache on every commit and sends the entire repo
  into the build context including `node_modules`, test fixtures, and `.git`.
- `npm install` (or `pnpm install` without `--offline`) inside Docker when `pnpm fetch`
  has not run — hits the registry on every build even if nothing changed.
- Not using `pnpm deploy` for the runtime stage — copying the entire workspace
  `node_modules` into the runtime image includes dev dependencies and all workspace
  package source, bloating the image 5-10x.
- Running `pnpm install` without `--frozen-lockfile` in CI — allows silent lockfile
  mutations and non-deterministic builds.
- Using `--mount=type=cache` without a unique `id` — when multiple app builds share the
  same runner, cache mount collisions cause corruption. Use `id=pnpm-store-${APP}`.

## Gotchas

- `pnpm fetch` only respects `pnpm-lock.yaml`, not `package.json`. If you add a
  dependency without regenerating the lockfile, `pnpm fetch` will miss it and
  `pnpm install --offline` will fail.
- `pnpm deploy` resolves workspace protocol (`workspace:*`) references by copying the
  built output of those packages, not their source. You must build dependent workspace
  packages before running `pnpm deploy`.
- The `corepack prepare pnpm@latest` line in the Dockerfile installs the latest pnpm,
  which may differ from the version declared in `package.json#packageManager`. Pin to an
  exact version: `corepack prepare pnpm@9.4.0 --activate`.
- `COPY apps/*/package.json ./apps/` requires Buildx/BuildKit; classic `docker build`
  does not support glob `COPY`. Always ensure `DOCKER_BUILDKIT=1`.
- On GitHub Actions, the GHA cache backend has a 10 GB cap. Docker image layers for a
  large monorepo can hit this limit quickly. Use `mode=max` only on the base stages;
  consider `mode=min` for app-specific stages to stay under the cap.

## Verification

```bash
# Cold build (first run) — measure time
time docker build --build-arg APP=api -t api:test .

# Warm build (source change only) — should be much faster
echo "// touch" >> apps/api/src/index.ts
time docker build --build-arg APP=api -t api:test .
# Expect: Stage 1 and 2 CACHED; only Stage 3/4 rebuilt

# Verify runtime image size
docker images api:test --format "{{.Size}}"
# Target: < 200 MB for a typical Node.js API

# Verify no dev dependencies in runtime image
docker run --rm api:test node -e "require('vitest')" 2>&1
# Expected: Cannot find module 'vitest' (dev dep not present)

# Verify workspace internal dep resolved correctly
docker run --rm api:test node -e "require('@repo/shared')" && echo OK
```

## Related

- pnpm-workspaces-monorepo.md
- docker-multi-stage-build-optimization.md
- docker-workers-ci-artifacts.md
- github-self-hosted-runners.md
- buildkit-cache-mount-concurrency-and-integrity.md

## Sources

- https://pnpm.io/cli/fetch
- https://pnpm.io/cli/deploy
- https://docs.docker.com/build/cache/
- https://docs.docker.com/build/cache/backends/gha/
- https://docs.github.com/en/actions/use-cases-and-examples/publishing-packages/publishing-docker-images
- https://turbo.build/repo/docs/guides/tools/docker
