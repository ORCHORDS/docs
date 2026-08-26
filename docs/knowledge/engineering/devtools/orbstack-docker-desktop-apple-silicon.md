# OrbStack vs Docker Desktop on Apple Silicon

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

`docker run` on a MacBook Pro M-series takes 20–40 seconds to
produce the first container; `wrangler dev` inside a container
stalls waiting for the x86 image to emulate via Rosetta; file
watching inside bind-mounted volumes misses events. Docker Desktop
4.x consumes 2–4 GB of memory at idle and noticeably slows the
machine under sustained container workloads.

## Context

The platform team's development machines are Apple Silicon (M2 /
M3). Production workers run on Cloudflare's x86-64 Linux fleet.
The gap matters for two workflows: running the full `docker compose`
stack for local integration testing, and running `cloudflare/
wrangler` dev containers that ship as x86 images. OrbStack has
been the team's chosen runtime since late 2024 because its
Virtualization.framework VM starts in under two seconds and its
VirtioFS implementation handles file events correctly.

## VM Architecture Comparison

| Dimension              | OrbStack            | Docker Desktop        | Colima / Lima         |
|------------------------|---------------------|-----------------------|-----------------------|
| VM hypervisor          | macOS Virt.fw       | macOS Virt.fw (4.x+)  | QEMU / Virt.fw        |
| Cold start             | ~1–2 s              | 10–30 s               | 5–15 s (Virt.fw)      |
| Idle RAM               | ~150 MB             | 1.5–3 GB              | ~200 MB               |
| File sharing           | VirtioFS (fast)     | VirtioFS (4.x+)       | VirtioFS or 9p        |
| GUI                    | menu-bar app        | full Electron app      | none (CLI only)       |
| License (teams)        | paid after trial    | paid for >250 emp.    | MIT (free)            |
| Rosetta x86 emulation  | built-in            | built-in              | manual QEMU config    |

OrbStack and Docker Desktop both sit on `com.apple.Virtualization`
since macOS 13; the startup gap comes from OrbStack keeping a
pre-warmed VM resident rather than starting fresh each session.

## Rosetta 2 x86 Emulation for Cloudflare / Wrangler

Wrangler's `cloudflare/wrangler` Docker image ships as `linux/
amd64`. On Apple Silicon this runs under emulation. OrbStack
transparently enables Rosetta 2 inside the VM — no extra flags
needed:

```bash
# Pulls the amd64 image and runs under Rosetta automatically
docker run --platform linux/amd64 \
  -v $(pwd):/app -w /app \
  cloudflare/wrangler:latest dev
```

Docker Desktop requires the same `--platform` flag but must have
"Use Rosetta for x86_64/amd64 emulation on Apple Silicon" enabled
in Settings → General. Colima needs explicit VM configuration:

```bash
# Colima with Rosetta and VirtioFS
colima start \
  --arch x86_64 \
  --vm-type vz \
  --vz-rosetta \
  --mount-type virtiofs \
  --cpu 4 --memory 8
```

Native arm64 builds of wrangler (installed via npm/pnpm outside
Docker) avoid emulation entirely and are faster for pure JS
workers. Use Docker only when the full compose stack must mirror
production OS-level dependencies.

## File System Bind Mount Performance

Bind mounts under QEMU (old Colima default) are 3–10x slower than
native FS access — `npm install` inside a bind-mounted volume can
take minutes. VirtioFS closes most of the gap.

```bash
# Measure write throughput inside the container
docker run --rm -v $(pwd):/bench alpine \
  sh -c "dd if=/dev/zero of=/bench/test.dat bs=1M count=256 && rm /bench/test.dat"
```

Expected results (approximate, M3 MacBook Pro):
- OrbStack VirtioFS:   ~800 MB/s
- Docker Desktop VirtioFS: ~600–750 MB/s
- Colima VirtioFS:    ~500–700 MB/s
- Colima QEMU + 9p:   ~50–120 MB/s

For file-watching (Vite, Bun, `wrangler dev --watch`), the key
metric is inotify latency. VirtioFS passes inotify events from the
host FS — OrbStack's implementation adds <5 ms latency, making hot
reload feel native.

## Lima / Colima as Lightweight Alternatives

Lima is the open-source VM layer that Colima wraps. It is free,
MIT-licensed, and suits CI machines where OrbStack's GUI is unused:

```yaml
# ~/.lima/default/lima.yaml
vmType: vz          # macOS Virtualization.framework
rosetta:
  enabled: true
  binfmt: true
mountType: virtiofs
mounts:
  - location: "~"
    writable: true
```

```bash
# Start Lima VM with the config above
limactl start --name default ~/.lima/default/lima.yaml

# Use Docker inside Lima via socket
export DOCKER_HOST=unix://$HOME/.lima/default/sock/docker.sock
docker ps
```

Colima wraps Lima with sane defaults and a `colima start` one-liner
at the cost of less flexibility. Neither offers OrbStack's instant
restart or the menu-bar status panel — acceptable tradeoffs for a
CI runner or a developer who prefers zero background GUI.

## Anti-patterns

- Running QEMU-emulated x86 containers for CPU-intensive tasks
  (test suites, builds) when a native arm64 image or binary exists.
- Mounting the entire home directory (`-v ~:/home`) — VirtioFS
  still scans the mount root; scope mounts to the project directory.
- Relying on `host.docker.internal` to reach macOS services from
  inside a container with Colima — the hostname is available in
  OrbStack and Docker Desktop but not in Lima without extra config.
- Disabling Rosetta and then wondering why `linux/amd64` images
  fail with `exec format error` on M-series hardware.

## Gotchas

- OrbStack and Docker Desktop cannot run simultaneously — only one
  VM provider can own `/var/run/docker.sock` at a time. Switch
  with `orbctl use-docker` / `orbctl unuse-docker`.
- Docker Compose `depends_on` with `condition: service_healthy`
  can time out on first run when the x86 image is being pulled and
  Rosetta JIT-compiled simultaneously — add a `start_period` to
  the health check.
- Colima's Docker context must be activated explicitly:
  `docker context use colima` — forgetting this causes commands to
  hit OrbStack's or Desktop's socket instead.
- File owner/group mapping inside the container differs between
  runtimes; `--userns=keep-id` (Podman) has no Docker equivalent —
  use numeric UID in the Dockerfile (`USER 1000`) for portability.

## Verification

```bash
# Confirm OrbStack is active Docker context
docker context ls

# Check Rosetta is available inside the VM
docker run --rm --platform linux/amd64 alpine uname -m
# Expected: x86_64

# Confirm VirtioFS (OrbStack)
docker info | grep "Operating System"
docker system info | grep "Docker Root Dir"
```

## Related

- `devtools/docker-desktop-setup.md`
- `devtools/docker-compose-dev.md`
- `devtools/devcontainer-json.md`
- `devtools/wrangler-dev-local-mocking.md`
- `infra/cloudflare-workers-architecture.md`

## Source URLs (verified 2026-08-17)

- https://orbstack.dev/
- https://docs.orbstack.dev/docker/
- https://lima-vm.io/docs/config/rosetta/
- https://github.com/abiosoft/colima
- https://docs.docker.com/desktop/settings/mac/#use-rosetta-for-x86amd64-emulation-on-apple-silicon
