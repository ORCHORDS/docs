# multi-arch-builds-arm-x86

**Issue:** Building container images for multiple CPU architectures (x86_64/amd64 + ARM64) so the same image runs on Intel/AMD servers, AWS Graviton, Apple Silicon, and ARM cloud instances — without maintaining separate images per arch
**Date:** 2026-08-12
**Status:** documented

## Symptom
You build a Docker image on your M3 MacBook (ARM64) and push it.
It deploys to your production cluster on Intel Xeon nodes
(amd64). Pods crash with `exec format error` — the binary inside is
ARM, the host is x86. You now maintain two image tags (`api-arm64`,
`api-amd64`) and your deploy scripts are a mess of arch detection.

## Root cause
**Single-arch images only run on one CPU architecture.** The fix
is a multi-arch (manifest-list) image: one tag (`api:v1.2.0`) that
contains both architectures, and the container runtime pulls the
right one automatically based on the host.

**Source:** AWS Graviton (ARM) is 20-40% cheaper than x86 for many
workloads. Apple Silicon dev machines are ARM. Azure, GCP, and OCI
all offer ARM instances. By 2026, multi-arch is the default, not
the exception.

## The "buildx multi-arch" pattern

Use Docker Buildx with QEMU to build both architectures in one
command (cross-compilation via emulation):

```bash
# Create a builder instance (once)
docker buildx create --name multiarch --use

# Build and push a multi-arch image
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag registry.example.com/api:v1.2.0 \
  --push \
  .
```

The registry now holds a manifest list:
```bash
# Verify both architectures are present
docker buildx imagetools inspect registry.example.com/api:v1.2.0
# Output:
#  linux/amd64  - sha256:abc123...
#  linux/arm64  - sha256:def456...
```

The container runtime pulls the correct arch automatically.

## The "Dockerfile" — arch-aware

Write a Dockerfile that works on both architectures. Avoid
hardcoding arch-specific binaries:

```dockerfile
# Works on both amd64 and arm64
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S app && adduser -S app -G app
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/dist ./dist
USER app
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

Node, Python, Go, Rust base images all publish multi-arch tags, so
`FROM node:22-alpine` works on both platforms automatically.

## The "native multi-arch CI" pattern (faster)

QEMU emulation is slow (5-10x). For faster CI builds, use native
runners per arch and merge the manifests:

```yaml
# .github/workflows/multiarch.yml
name: build-multiarch
on:
  push:
    tags: ['v*']

jobs:
  build-amd64:
    runs-on: ubuntu-latest    # native amd64
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/build-push-action@v6
        with:
          platforms: linux/amd64
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}-amd64
          push: true

  build-arm64:
    runs-on: ubuntu-24.04-arm   # GitHub native ARM runners (2025+)
    steps:
      - uses: actions/checkout@v4
      - uses: docker/build-push-action@v6
        with:
          platforms: linux/arm64
          tags: ghcr.io/${{ github.repository }}:${{ github.ref_name }}-arm64
          push: true

  merge-manifest:
    needs: [build-amd64, build-arm64]
    runs-on: ubuntu-latest
    steps:
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
      - run: |
          docker buildx imagetools create \
            -t ghcr.io/${{ github.repository }}:${{ github.ref_name }} \
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}-amd64 \
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}-arm64
```

Native builds are 3-5x faster than QEMU.

## The "Go cross-compile" pattern (fastest)

Go cross-compiles natively — no QEMU needed. Build both arch
binaries in one job, package into a multi-arch image:

```dockerfile
# Dockerfile.go-multiarch
FROM --platform=$BUILDPLATFORM golang:1.23 AS builder
ARG TARGETOS
ARG TARGETARCH
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -o /server ./cmd/server

FROM scratch
COPY --from=builder /server /server
ENTRYPOINT ["/server"]
```

Buildx injects `TARGETARCH` automatically. No emulation overhead
for the compile step.

## The "verify in Kubernetes" pattern

Ensure your cluster nodes can pull the right arch:

```bash
# Check node architectures
kubectl get nodes -o custom-columns="NAME:.metadata.name,ARCH:.status.nodeInfo.architecture"

# Deploy the multi-arch image — each node pulls its arch
kubectl create deployment api --image=registry.example.com/api:v1.2.0
```

If a node is `arm64` and your image only has `amd64`, the pod stays
in `ImagePullBackOff`.

## Verification
- **Manifest has both archs:** `docker buildx imagetools inspect
  <image>` lists `linux/amd64` and `linux/arm64`
- **Pulls correct arch:** run `docker pull` on an ARM machine, then
  `docker inspect <image> | grep Architecture` shows `arm64`
- **Pods schedule on both:** deploy to a mixed-arch cluster,
  `kubectl get pods -o wide` shows pods running on both arm64 and
  amd64 nodes
- **No `exec format error`:** check `kubectl logs` — no `exec user
  process caused: exec format error`

## Gotchas
- **QEMU is slow and sometimes wrong.** Emulated builds can produce
  subtly broken binaries (signal handling, atomics). For production,
  prefer native ARM runners or Go/Rust cross-compilation. Use QEMU
  only for dev/testing.
- **`FROM python:3.13` is multi-arch, but C-extension deps may not
  be.** A `pip install` of a package with native C code (numpy,
  lxml, psycopg2) needs wheels for both archs. Most popular packages
  ship arm64 wheels now, but obscure ones do not. Check
  `pip install <pkg>` on both archs.
- **Tag collisions break rollbacks.** If you push `api:v1.2.0` as
  amd64-only first, then re-push as multi-arch, some clients may
  have cached the amd64-only manifest. Always push the final
  multi-arch manifest as the canonical tag, and use `--push` in one
  atomic `buildx build` command.
- **`BUILDPLATFORM` vs `TARGETPLATFORM`.** `BUILDPLATFORM` is the
  arch doing the building; `TARGETPLATFORM` is the arch being built
  *for*. In a Go multi-stage build, use `--platform=$BUILDPLATFORM`
  on the builder stage so Go runs natively while cross-compiling.
- **Registry must support manifest lists.** Very old or minimal
  registries may not. ECR, GAR, GHCR, Docker Hub, and Harbor all
  support manifest lists (OCI image index) in 2026. If `kubectl`
  gets `manifest invalid`, check your registry version.
- **Graviton perf needs tuning.** An amd64 image running on Graviton
  via emulation is *slower* than native amd64. Multi-arch images let
  Graviton run the native arm64 variant, which is 20-40% faster and
  cheaper than equivalent x86 — but only if the arm64 build is
  actually present in the manifest.

## Related
- `docker-multi-stage-build.md`
- `container-image-tagging.md`
- `docker-layer-caching-ci.md`
- `docker-security-scanning.md`
- `finops-cost-optimization.md`
- Docker buildx multi-arch: https://docs.docker.com/build/building/multi-platform/
- GitHub ARM runners: https://github.blog/changelog/2025-01-16-linux-arm64-hosted-runners-now-available/
- AWS Graviton: https://aws.amazon.com/ec2/graviton/
