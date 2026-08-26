# Building Multi-Platform Docker Images with WASM Modules for Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You have a Rust library that must run both inside a Docker container (for local dev / CI) and in Cloudflare Workers (compiled to WASM). You need a single Dockerfile that produces `linux/amd64` and `linux/arm64` images, extracts the `.wasm` artifact, and publishes it to R2 for Workers to fetch at cold start.

## Context

Two delivery strategies exist for WASM in Workers:

| Strategy | Bundle with `wrangler` | Fetch from R2 at cold start |
|---|---|---|
| Upload limit | 10 MB compressed | No Worker size limit for R2 objects |
| Cold start latency | Zero (bundled) | +50–300 ms (R2 fetch, once per isolate) |
| Update cadence | Requires Worker redeploy | Upload new `.wasm` to R2, Worker picks up next cold start |
| Best for | Small WASM (< 5 MB) | Large WASM (> 5 MB) or frequent updates |

This article covers the multi-platform Docker + R2 approach. For small WASM see `wrangler.toml` bundling notes below.

Prerequisites:
- Docker Desktop >= 4.28 with `buildx` enabled
- Rust toolchain + `wasm-pack` or `cargo build --target wasm32-unknown-unknown`
- `wrangler` >= 3.50 for R2 uploads
- GitHub Actions runner: `ubuntu-latest` with QEMU for `arm64` emulation

---

## Dockerfile: Cross-Compile Rust to WASM and Native

```dockerfile
# syntax=docker/dockerfile:1.7
# Build argument: TARGETPLATFORM is injected by buildx (linux/amd64 | linux/arm64)
FROM --platform=$BUILDPLATFORM rust:1.78-slim AS rust-build

ARG TARGETPLATFORM
ARG BUILDPLATFORM

WORKDIR /build
COPY Cargo.toml Cargo.lock ./
COPY src/ ./src/

# Install wasm-pack and the WASM target once per build
RUN rustup target add wasm32-unknown-unknown && \
    cargo install wasm-pack --version 0.12.1 --locked

# Cross-compile native binary for TARGETPLATFORM
RUN case "${TARGETPLATFORM}" in \
      "linux/amd64") RUST_TARGET=x86_64-unknown-linux-musl ;; \
      "linux/arm64") RUST_TARGET=aarch64-unknown-linux-musl ;; \
      *) echo "Unsupported platform: ${TARGETPLATFORM}"; exit 1 ;; \
    esac && \
    rustup target add ${RUST_TARGET} && \
    cargo build --release --target ${RUST_TARGET} && \
    cp target/${RUST_TARGET}/release/myapp /build/myapp-native

# WASM compilation is platform-independent (targets wasm32, runs on any host)
RUN wasm-pack build --target no-modules --release --out-dir /build/wasm-out -- --no-default-features

# ---- Runtime image (platform-specific) ----
FROM --platform=$TARGETPLATFORM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

COPY --from=rust-build /build/myapp-native /usr/local/bin/myapp
# Embed WASM inside image for local dev use; CI extracts and uploads to R2 separately
COPY --from=rust-build /build/wasm-out/myapp_bg.wasm /opt/wasm/myapp.wasm

ENTRYPOINT ["/usr/local/bin/myapp"]
```

---

## GitHub Actions: Matrix Build + R2 Publish

```yaml
# .github/workflows/build-and-publish.yml
name: Build multi-platform images and publish WASM

on:
  push:
    branches: [main]
    tags:     ['v*']

permissions:
  contents: read
  packages: write
  id-token: write

jobs:
  build:
    name: Build (${{ matrix.platform }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        platform: [linux/amd64, linux/arm64]

    steps:
      - uses: actions/checkout@v4

      - name: Set up QEMU (needed for arm64 emulation on amd64 runner)
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push (platform-specific digest)
        id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          platforms: ${{ matrix.platform }}
          push: true
          cache-from: type=gha,scope=${{ matrix.platform }}
          cache-to:   type=gha,mode=max,scope=${{ matrix.platform }}
          outputs: type=image,name=ghcr.io/${{ github.repository }},push-by-digest=true,name-canonical=true,push=true

      - name: Export digest for merge job
        run: |
          mkdir -p /tmp/digests
          digest="${{ steps.build.outputs.digest }}"
          touch "/tmp/digests/${digest#sha256:}"

      - uses: actions/upload-artifact@v4
        with:
          name: digest-${{ strategy.job-index }}
          path: /tmp/digests/*
          retention-days: 1

  merge-and-publish-wasm:
    name: Merge manifests + publish WASM to R2
    runs-on: ubuntu-latest
    needs: build

    steps:
      - uses: actions/checkout@v4

      - uses: actions/download-artifact@v4
        with:
          path: /tmp/digests
          merge-multiple: true

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Create and push multi-arch manifest
        run: |
          REPO="ghcr.io/${{ github.repository }}"
          TAG="${GITHUB_REF_NAME:-latest}"
          DIGESTS=$(ls /tmp/digests | awk '{print "'"${REPO}@sha256:"'"$0}' | tr '\n' ' ')
          docker buildx imagetools create -t ${REPO}:${TAG} -t ${REPO}:latest ${DIGESTS}

      - name: Extract WASM from amd64 image and upload to R2
        env:
          CF_ACCOUNT_ID:  ${{ vars.CLOUDFLARE_ACCOUNT_ID }}
          R2_BUCKET:      wasm-artifacts
          WASM_KEY:       myapp/${{ github.ref_name }}/myapp.wasm
        run: |
          # Pull the amd64 image to extract the WASM artifact
          docker pull --platform linux/amd64 ghcr.io/${{ github.repository }}:latest
          docker create --name extract ghcr.io/${{ github.repository }}:latest
          docker cp extract:/opt/wasm/myapp.wasm ./myapp.wasm
          docker rm extract

          # Upload to R2 via wrangler
          npx wrangler r2 object put "${R2_BUCKET}/${WASM_KEY}" \
            --file ./myapp.wasm \
            --content-type application/wasm
          echo "Published WASM: r2://${R2_BUCKET}/${WASM_KEY}"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Worker: Fetch WASM from R2 at Cold Start

```typescript
// src/index.ts
import { instantiate } from '../wasm-out/myapp.js';  // generated by wasm-pack

export interface Env {
  WASM_BUCKET: R2Bucket;
  WASM_KEY:    string;   // e.g. "myapp/v1.2.3/myapp.wasm"
}

let wasmInstance: WebAssembly.Instance | null = null;

async function getWasm(env: Env): Promise<WebAssembly.Instance> {
  if (wasmInstance) return wasmInstance;  // cached per isolate lifetime

  const obj = await env.WASM_BUCKET.get(env.WASM_KEY);
  if (!obj) throw new Error(`WASM not found: ${env.WASM_KEY}`);

  const bytes = await obj.arrayBuffer();
  const module = await WebAssembly.compile(bytes);
  wasmInstance = await WebAssembly.instantiate(module, {});
  return wasmInstance;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const wasm = await getWasm(env);
    // Call exported WASM function
    const result = (wasm.exports.process as CallableFunction)(42);
    return Response.json({ result });
  },
};
```

---

## Size and Cold-Start Comparison

| Delivery | `.wasm` size | Cold start overhead | Notes |
|---|---|---|---|
| Bundled with wrangler | < 5 MB | 0 ms (embedded) | Counts toward 10 MB compressed Worker size limit |
| R2 fetch (first request) | Any | 80–300 ms | Cached for isolate lifetime; acceptable for batch/background Workers |
| R2 fetch (subsequent) | Any | 0 ms | Module cached in `wasmInstance` global |

---

## Bundling WASM with wrangler (Small Modules)

```toml
# wrangler.toml — for WASM < 5 MB
[[wasm_modules]]
binding = "MY_WASM"
path    = "./wasm-out/myapp_bg.wasm"
```

```typescript
// Access via env.MY_WASM (already a WebAssembly.Module)
const instance = await WebAssembly.instantiate(env.MY_WASM, {});
```

---

## Anti-patterns

- **Using `--platform linux/amd64` only**: arm64 runners are faster and cheaper on GitHub Actions; missing arm64 images causes failures on Apple Silicon Macs running local Docker.
- **Recompiling WASM per platform**: WASM is platform-independent — compile once on the build host, copy into both platform images.
- **Fetching WASM on every request**: cache the `WebAssembly.Instance` in a module-level variable; it persists for the isolate lifetime.
- **Storing `.wasm` in the Worker bundle when it exceeds 5 MB compressed**: this hits the Worker upload size limit.

## Gotchas

- `wasm-pack build --target no-modules` is required for Workers (not `--target web` or `--target bundler`).
- `QEMU` emulation for `arm64` is ~4x slower than native. Cache Rust build artifacts aggressively with `type=gha`.
- `docker buildx build --platform linux/amd64,linux/arm64` in a single `build-push-action` call is serial; split into a matrix for parallel builds.
- R2 does not serve WASM with `Content-Type: application/wasm` by default — set it explicitly on upload.

## Verification

```bash
# Confirm multi-arch manifest
docker buildx imagetools inspect ghcr.io/your-org/myapp:latest

# Verify WASM in R2
npx wrangler r2 object get wasm-artifacts/myapp/v1.2.3/myapp.wasm --file /tmp/check.wasm
file /tmp/check.wasm   # should print: WebAssembly (wasm) binary module
```

## Related

- `aws-s3-r2-migration-workers-pipeline.md`
- `cloudflare-workers-wasm-performance.md`
- `rust-wasm-workers-bindings.md`

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/webassembly/
- https://docs.docker.com/build/building/multi-platform/
- https://rustwasm.github.io/wasm-pack/book/commands/build.html
- https://developers.cloudflare.com/r2/api/workers/workers-api-usage/
