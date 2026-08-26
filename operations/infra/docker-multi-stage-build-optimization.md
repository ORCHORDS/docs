# Docker Multi-Stage Build Optimization

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Node.js container images ballooning past 1 GB due to bundled
`devDependencies`, build tools, and the full `node_modules` tree.
Cold-start latency in Kubernetes increases proportionally with
image size, and registry storage costs compound over hundreds of
daily builds.

## Context

Multi-stage Dockerfiles allow the build toolchain and source tree
to live in one throwaway stage while the final image receives only
the compiled artifacts and production dependencies. This entry
covers the `FROM ... AS build / FROM ... AS final` pattern,
pruning dev dependencies with `pnpm --prod`, `.dockerignore` best
practices, layer-cache ordering, distroless base images, and
BuildKit cache mounts for the pnpm content-addressable store.

All examples assume a TypeScript/Node 22 project managed with pnpm.

## 1. .dockerignore Best Practices

A missing or incomplete `.dockerignore` file invalidates the
build-stage layer cache on every source change, even when
`package.json` has not changed. Exclude everything that is not
needed to install dependencies or compile code:

```dockerignore
# Version control
.git
.gitignore

# Local environment
.env
.env.*
!.env.example

# Output / generated
dist/
build/
coverage/

# Editor artifacts
.vscode/
.idea/
*.swp

# OS noise
.DS_Store
Thumbs.db

# pnpm local store (mounts handle this in CI)
.pnpm-store/

# Test files (not needed inside image)
**/*.test.ts
**/*.spec.ts
```

Keep the `.dockerignore` in sync with `.gitignore`; divergence is
a common source of cache invalidation bugs.

## 2. Layer Cache Ordering

Copy dependency manifests before source files. Docker invalidates
each subsequent layer when a file changes; placing the slow
`pnpm install` layer after the fast manifest copy means source
edits do not trigger a full install:

```dockerfile
# syntax=docker/dockerfile:1
FROM node:22-slim AS base
RUN npm install -g pnpm@9
WORKDIR /app

# --- dependency stage (cached unless lock file changes) ---
FROM base AS deps
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

# --- build stage ---
FROM deps AS build
COPY tsconfig*.json ./
COPY src/ ./src/
RUN pnpm build

# --- production deps only ---
FROM base AS prod-deps
COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prod
```

The `--mount=type=cache` directive requires BuildKit
(`DOCKER_BUILDKIT=1` or BuildKit-native CLI). The pnpm content-
addressable store is reused across builds on the same host,
converting installs from network fetches to local hard links.

## 3. Final Stage with Distroless

The final stage copies only compiled output and production
`node_modules` into a minimal base image:

```dockerfile
FROM gcr.io/distroless/nodejs22-debian12:nonroot AS final

WORKDIR /app

# Copy prod node_modules from prod-deps stage
COPY --from=prod-deps /app/node_modules ./node_modules

# Copy compiled artifacts from build stage
COPY --from=build /app/dist ./dist

# Copy package.json for runtime metadata (no scripts run here)
COPY package.json ./

EXPOSE 8080
CMD ["dist/server.js"]
```

`distroless/nodejs22-debian12:nonroot` ships without a shell,
package manager, or root user. Vulnerability scanners report
dramatically fewer CVEs compared to `node:22-alpine` or `node:22-
slim` because the attack surface is stripped to the Node runtime
and its shared libraries only.

## 4. Image Size Comparison

Measured against a representative TypeScript API service with
~120 npm dependencies (40 production, 80 dev):

```
+------------------------------------------+----------+---------+
| Base image / build strategy              | Size     | Layers  |
+------------------------------------------+----------+---------+
| node:22 (single stage, all deps)         | 1.31 GB  |   12    |
| node:22-alpine (all deps)                | 412 MB   |   11    |
| node:22-slim + pnpm --prod               | 228 MB   |   10    |
| node:22-slim multi-stage + pnpm --prod   | 198 MB   |    6    |
| distroless/nodejs22 multi-stage + pnpm   | 143 MB   |    4    |
+------------------------------------------+----------+---------+
```

The distroless multi-stage build is 89% smaller than the naive
single-stage build, reducing registry bandwidth and pull latency.

## 5. Pruning Dev Dependencies with pnpm

`pnpm install --prod` removes `devDependencies` from
`node_modules` in place. The `--frozen-lockfile` flag ensures
the lock file is not rewritten inside the container:

```bash
# Verify locally before committing to Dockerfile
pnpm install --frozen-lockfile --prod
du -sh node_modules/   # should reflect production size only
```

For monorepos using pnpm workspaces, deploy only the specific
package's production closure:

```bash
pnpm deploy --filter=example project-api --prod /app/deploy
```

Copy `/app/deploy` into the final stage instead of the root
`node_modules`.

## Anti-patterns

- Copying `node_modules` from the host into the image. The host
  platform (macOS, Windows) may have native addons compiled for
  the wrong architecture.
- Running `pnpm install` in the final stage. The final stage
  should contain no build tools.
- Using `COPY . .` before `COPY package.json pnpm-lock.yaml ./`.
  This collapses the dependency cache into the source-change
  layer, making every code edit trigger a full install.
- Setting `NODE_ENV=production` in the build stage when
  `devDependencies` are needed to compile TypeScript. Set it only
  in the prod-deps and final stages.

## Gotchas

- `distroless` images have no shell. Debug with
  `docker run --entrypoint=/busybox/sh gcr.io/distroless/...`
  using the `debug` tag variant during development.
- BuildKit cache mounts are host-local; they are not shared across
  CI runners by default. Use `cache-from` and `cache-to` with
  a registry backend (`type=registry`) for distributed CI caching.
- `pnpm-lock.yaml` must be committed. A missing lock file forces
  `pnpm install` to resolve the dependency graph on every build.

## Verification

```bash
# Build with BuildKit
DOCKER_BUILDKIT=1 docker build \
  --target final \
  --tag example project-api:local \
  .

# Check compressed image size
docker image ls example project-api:local

# Confirm no shell in final image (should exit non-zero)
docker run --rm example project-api:local sh

# Smoke test
docker run --rm -p 8080:8080 example project-api:local &
curl http://localhost:8080/health
```

## Related

- `ci-docker-buildkit-cache.md`
- `kubernetes-image-pull-policy.md`
- `distroless-debugging-guide.md`

## Source URLs (verified 2026-08-17)

- https://docs.docker.com/build/guide/multi-stage/
- https://github.com/GoogleContainerTools/distroless
- https://pnpm.io/cli/install#--prod
- https://docs.docker.com/build/cache/
- https://pnpm.io/filtering#--filter-package_name
