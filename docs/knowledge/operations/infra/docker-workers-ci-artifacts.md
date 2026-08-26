# Docker Multi-Stage Builds for Cloudflare Workers CI Artifacts

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

CI pipelines that build Cloudflare Workers with `wrangler build` or `esbuild` pull full node_modules on every run, spend 60-90 seconds installing dependencies, and push multi-hundred-MB Docker images to the registry even though the deployable artifact is a single sub-1 MB ESM bundle. Build times inflate as the monorepo grows, and cache misses are frequent because the Dockerfile layer order is wrong for the pnpm content-addressable store.

## Context

Cloudflare Workers compile to a single ESM bundle (or a module graph) that `wrangler deploy` pushes to the Cloudflare network. The build toolchain — TypeScript compiler, esbuild, wrangler, pnpm — is needed only during compilation; the final CI artifact is the `dist/` directory containing `worker.js` (and optional `__STATIC_CONTENT_MANIFEST` for asset binding). example project uses a pnpm monorepo with separate Workers packages for the API layer, queue consumers, and scheduled cron jobs. A well-structured multi-stage Dockerfile isolates the build environment, caches the pnpm store, and produces a minimal image (or a pure artifact export) that the CD stage uploads via `wrangler deploy --dry-run` or direct API upload. This differs from general container optimization: Workers are never containerized for runtime — Docker is used purely to produce and transport the compiled bundle artifact reproducibly across CI agents.

## Stage 1 — Dependency Installation with BuildKit Cache Mounts

```dockerfile
# syntax=docker/dockerfile:1.9
ARG NODE_VERSION=22-alpine

# ── Stage 1: install deps ───────────────────────────────────────────────────
FROM node:${NODE_VERSION} AS deps

# pnpm via corepack (version pinned in package.json > packageManager)
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /repo

# Copy lockfile and workspace manifests first for cache stability
COPY pnpm-lock.yaml ./
COPY pnpm-workspace.yaml ./
COPY package.json ./

# Worker package manifests (only package.json files, no source)
COPY apps/api-worker/package.json          ./apps/api-worker/
COPY apps/queue-consumer/package.json      ./apps/queue-consumer/
COPY apps/cron-worker/package.json         ./apps/cron-worker/
COPY packages/shared/package.json          ./packages/shared/

# Frozen install with BuildKit cache mount on the pnpm content store
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile --prefer-offline
```

## Stage 2 — Build the Worker Bundle

```dockerfile
# ── Stage 2: build ─────────────────────────────────────────────────────────
FROM deps AS build

# Copy all source after deps are cached
COPY . .

# Build argument selects which Worker to compile
ARG WORKER_NAME=api-worker

# Run wrangler build (or tsc + esbuild for library workers)
# wrangler build produces dist/worker.js via esbuild under the hood
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm --filter "@example project/${WORKER_NAME}" run build

# Verify the artifact exists and print its size
RUN ls -lh apps/${WORKER_NAME}/dist/worker.js && \
    echo "Bundle size: $(wc -c < apps/${WORKER_NAME}/dist/worker.js) bytes"
```

## Stage 3 — Minimal Artifact Image

```dockerfile
# ── Stage 3: artifact export ────────────────────────────────────────────────
FROM scratch AS artifact

ARG WORKER_NAME=api-worker

# Copy only the compiled bundle and wrangler.toml
COPY --from=build /repo/apps/${WORKER_NAME}/dist/          /dist/
COPY --from=build /repo/apps/${WORKER_NAME}/wrangler.toml  /wrangler.toml

# Stage 4 is used only when the image runs wrangler deploy inside Docker
# (e.g., for air-gapped environments or consistent CLI version pinning)
FROM node:22-alpine AS deployer

RUN corepack enable && corepack prepare pnpm@latest --activate
RUN npm install -g wrangler@latest --no-save

ARG WORKER_NAME=api-worker
COPY --from=build /repo/apps/${WORKER_NAME}/dist/         /deploy/dist/
COPY --from=build /repo/apps/${WORKER_NAME}/wrangler.toml /deploy/wrangler.toml

WORKDIR /deploy
ENTRYPOINT ["wrangler"]
CMD ["deploy", "--dry-run", "--outdir", "/deploy/dist"]
```

## wrangler.toml Build Configuration

Configure `wrangler.toml` so `wrangler build` produces deterministic output:

```toml
# apps/api-worker/wrangler.toml
name = "example project-api"
main = "src/index.ts"
compatibility_date = "2026-08-01"
compatibility_flags = ["nodejs_compat_v2"]

# esbuild options passed through wrangler
[build]
command = "pnpm run build:ts"       # optional pre-build step for codegen

[build.upload]
format = "modules"
main = "./dist/worker.js"
dir = "./dist"

# Source maps for error reporting (stripped before upload by wrangler)
[minify]
javascript = true

[[rules]]
type = "ESModule"
globs = ["**/*.js"]
fallthrough = false
```

Custom esbuild pipeline when wrangler's built-in bundler is not sufficient:

```typescript
// scripts/build.ts — custom esbuild for workers with complex import maps
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync('./package.json', 'utf8'));

await build({
  entryPoints: ['src/index.ts'],
  bundle: true,
  outfile: 'dist/worker.js',
  format: 'esm',
  target: 'es2022',
  platform: 'browser',   // Workers runtime is browser-like, not Node
  minify: process.env.NODE_ENV === 'production',
  sourcemap: process.env.NODE_ENV !== 'production',
  define: {
    'process.env.WORKER_VERSION': JSON.stringify(pkg.version),
    'process.env.BUILD_TIME': JSON.stringify(new Date().toISOString()),
  },
  // Externals that are provided by the Workers runtime
  external: ['cloudflare:workers', 'cloudflare:sockets'],
  logLevel: 'info',
});
```

## GitHub Actions Integration

```yaml
# .github/workflows/build-worker.yml
name: Build & Deploy Workers

on:
  push:
    branches: [main]
    paths:
      - 'apps/api-worker/**'
      - 'packages/shared/**'
      - 'pnpm-lock.yaml'

env:
  REGISTRY: ghcr.io
  IMAGE_PREFIX: ghcr.io/example-org/example-repo

jobs:
  build-api-worker:
    runs-on: ubuntu-24.04
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
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build artifact image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/workers.Dockerfile
          target: deployer
          build-args: WORKER_NAME=api-worker
          push: true
          tags: |
            ${{ env.IMAGE_PREFIX }}/api-worker:${{ github.sha }}
            ${{ env.IMAGE_PREFIX }}/api-worker:latest
          cache-from: type=gha,scope=api-worker
          cache-to: type=gha,mode=max,scope=api-worker
          provenance: true
          sbom: true

      - name: Extract bundle artifact
        run: |
          docker create --name extract ${{ env.IMAGE_PREFIX }}/api-worker:${{ github.sha }}
          docker cp extract:/deploy/dist ./worker-dist
          docker rm extract

      - name: Deploy to Cloudflare
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler@latest deploy \
            --config apps/api-worker/wrangler.toml \
            --outdir ./worker-dist \
            --env production
```

## Layer Cache Strategy for Monorepos

The key insight for monorepo Workers builds: copy workspace manifests before source files. Changes to one Worker's source do not invalidate the deps layer of sibling Workers.

```
Optimal layer order for cache hits:
  1. pnpm-lock.yaml               → invalidates on any dep change
  2. */package.json (all packages) → invalidates on manifest change
  3. RUN pnpm install              → cached when 1+2 unchanged
  4. COPY . .                      → source copy (always fresh)
  5. RUN pnpm build --filter X     → rebuilds only changed worker
```

Use `--filter` with `wrangler deploy` to scope deployments:

```bash
# Deploy only changed Workers in CI (affected packages only)
pnpm --filter "@example project/api-worker..." run build
pnpm --filter "@example project/queue-consumer..." run build
```

## Bundle Size Monitoring

```bash
# Add to CI to catch bundle size regressions
MAX_BUNDLE_BYTES=1048576   # 1 MB — Workers free limit is 1 MB compressed

BUNDLE_SIZE=$(wc -c < apps/api-worker/dist/worker.js)
if [ "$BUNDLE_SIZE" -gt "$MAX_BUNDLE_BYTES" ]; then
  echo "ERROR: Bundle ${BUNDLE_SIZE}B exceeds limit ${MAX_BUNDLE_BYTES}B"
  exit 1
fi

# Bundlephobia-style report with esbuild metafile
pnpm esbuild src/index.ts --bundle --metafile=meta.json --analyze
node -e "
  const m = require('./meta.json');
  const inputs = Object.entries(m.inputs)
    .sort((a,b) => b[1].bytes - a[1].bytes)
    .slice(0, 10);
  inputs.forEach(([k,v]) => console.log(v.bytes, k));
"
```

## Mobile vs Desktop Considerations

example project serves both web (Next.js on Pages) and mobile (React Native). The Docker build pipeline differs per target:

- **Workers (API, Queue, Cron)**: Single ESM bundle, no runtime container, Docker used only as CI build environment. Bundle must stay under Workers' 1 MB compressed limit (10 MB uncompressed) — mobile clients calling these Workers benefit from leaner cold-start times.
- **Next.js (Pages)**: Full Node.js multi-stage build produces a standalone server image OR a static export for Pages direct upload. Mobile web views hit the same Pages deployment; image optimization routes through Pages' Cloudflare Image Resizing.
- **React Native**: No Docker build for the mobile bundle — Expo EAS handles this. Workers serve as the API layer; mobile clients call them directly over HTTPS with no containerization involved.

## Anti-patterns

- Installing `wrangler` as a devDependency and letting it be included in the esbuild bundle — `wrangler` is a build-time CLI, never a runtime import
- Using `COPY . .` as the first layer before installing dependencies — every source file change busts the node_modules cache layer
- Building all Workers in a single Docker `RUN` step — prevents granular layer caching per Worker; use separate `--filter` build steps
- Pushing the full `node_modules` layer to the registry when only `dist/worker.js` is needed — use `FROM scratch AS artifact` or a `docker cp` extraction pattern
- Setting `platform: 'node'` in esbuild when targeting Cloudflare Workers — Workers use the browser runtime; Node-specific modules (fs, path, crypto) must use `nodejs_compat_v2` flag, not esbuild's Node platform

## Gotchas

- `wrangler build` does not respect `--outdir` in all versions — pin `wrangler` to a specific version in `package.json` and test after upgrades
- The `cloudflare:workers` and `cloudflare:sockets` module specifiers are runtime-only and must be marked external in esbuild; they do not exist in the build container
- BuildKit cache mounts (`--mount=type=cache`) are not populated on the first run in a fresh CI environment — the first build will be slow; subsequent builds in the same runner use the warm cache
- `wrangler deploy --dry-run --outdir` writes the final bundle (post wrangler transform) to the output dir; the file in `dist/` from esbuild may differ from what wrangler actually uploads (wrangler applies its own transforms)
- GitHub Actions GHA cache backend (`cache-from: type=gha`) has a 10 GB per-repo cap — scope caches by Worker name (`scope=api-worker`) to avoid eviction collisions

## Verification

```bash
# Build locally with the same Dockerfile used in CI
docker buildx build \
  --target deployer \
  --build-arg WORKER_NAME=api-worker \
  --output type=local,dest=./ci-out \
  -f docker/workers.Dockerfile \
  .

# Inspect the produced bundle
ls -lh ./ci-out/deploy/dist/
wc -c ./ci-out/deploy/dist/worker.js

# Validate the bundle with wrangler (does not deploy)
wrangler deploy --config apps/api-worker/wrangler.toml \
  --dry-run --outdir ./ci-out/deploy/dist

# Check cache hit rate across builds
docker buildx build --progress=plain ... 2>&1 | grep 'CACHED'
```

## Related

- `documentation/docs/policies/infra/docker-multi-stage-build-optimization.md`
- `documentation/docs/policies/infra/wrangler-deploys.md`
- `documentation/docs/policies/infra/wrangler-toml-multi-environment-config.md`
- `documentation/docs/policies/infra/cloudflare-workers-limits-resource-planning.md`
- `documentation/docs/policies/infra/pnpm-workspaces-monorepo.md`
- `documentation/docs/policies/infra/monorepo-2026.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#build
- https://developers.cloudflare.com/workers/wrangler/bundling/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://esbuild.github.io/api/#platform
- https://docs.docker.com/build/cache/optimize/
- https://docs.docker.com/reference/dockerfile/#run---mounttypecache
