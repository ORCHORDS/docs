# Self-Hosted GitHub Runner Fleet Management on Bare Metal

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

A growing monorepo's CI pipeline exhausts GitHub-hosted runner minutes budgets on large build jobs (React Native APK/IPA compilation, wrangler deploys, E2E Playwright suites), and Kubernetes-based ARC runners introduce pod scheduling latency and image-pull overhead that extends CI wall-clock time. Bare-metal hosts with local NVMe storage and pinned CPU/RAM deliver consistent, fast builds without container orchestration overhead — but fleet management, runner registration, OS patching, and ephemeral runner lifecycle become an operational burden without a structured approach.

## Context

example project's monorepo produces Cloudflare Workers bundles, a Next.js Pages deployment, and React Native builds for iOS and macOS (requiring macOS hosts). The Linux bare-metal fleet handles Workers builds, Playwright E2E, Docker image builds, and load testing. macOS hosts (Mac minis) build the React Native app. Each runner is ephemeral: a runner container (on Linux) or a fresh workspace (on macOS) is created per job, then torn down. The fleet is registered via GitHub's REST API using runner group tokens, monitored via Prometheus, and provisioned with Ansible. This article covers Linux bare-metal specifically; ARC/Kubernetes runners are documented separately.

## Hardware and OS Baseline

```
Recommended spec for Workers + Next.js build runners (Linux):
  CPU:  8-16 cores (AMD EPYC or Intel Xeon — avoid thermal throttling)
  RAM:  32 GB minimum (64 GB for parallel Playwright + Docker builds)
  Disk: 1 TB NVMe (local; network storage adds latency to pnpm cache reads)
  OS:   Ubuntu 24.04 LTS (minimal install, no GUI)
  Net:  1 Gbps (10 Gbps for large Docker layer pushes)
```

Partition layout optimized for CI workloads:

```
/           30 GB  (OS)
/var        50 GB  (apt cache, journals, Docker daemon storage)
/home       remaining NVMe  (runner workspaces, pnpm store, Docker volumes)
```

## Provisioning with Ansible

```yaml
# ansible/roles/github-runner/tasks/main.yml
- name: Create runner service user
  ansible.builtin.user:
    name: github-runner
    system: true
    shell: /bin/bash
    home: /home/github-runner
    create_home: true

- name: Install runner dependencies
  ansible.builtin.apt:
    name:
      - curl
      - git
      - docker-ce
      - docker-ce-cli
      - containerd.io
      - jq
      - unzip
    state: present
    update_cache: true

- name: Add runner user to docker group
  ansible.builtin.user:
    name: github-runner
    groups: docker
    append: true

- name: Download GitHub runner tarball
  ansible.builtin.get_url:
    url: "https://github.com/actions/runner/releases/download/v{{ runner_version }}/actions-runner-linux-x64-{{ runner_version }}.tar.gz"
    dest: /path/to/project runner_version }}.tar.gz
    checksum: "sha256:{{ runner_checksum }}"
    owner: github-runner
    group: github-runner

- name: Extract runner
  ansible.builtin.unarchive:
    src: /path/to/project runner_version }}.tar.gz
    dest: /path/to/project
    remote_src: true
    owner: github-runner
    group: github-runner
    creates: /path/to/project

- name: Register runner with GitHub API
  ansible.builtin.command:
    cmd: >
      /path/to/project
      --url https://github.com/example-org/example-repo
      --token {{ runner_registration_token }}
      --name {{ inventory_hostname }}
      --labels {{ runner_labels }}
      --runnergroup {{ runner_group }}
      --work /path/to/project
      --replace
      --unattended
  become: true
  become_user: github-runner
  no_log: true  # token is sensitive

- name: Install runner as systemd service
  ansible.builtin.command:
    cmd: /path/to/project install github-runner
  become: true
```

## Ephemeral Runner Pattern with Docker

Rather than running the GitHub runner binary directly on the bare-metal host (which accumulates state across jobs), run each job inside a Docker container that is created fresh per job and destroyed on completion. The host runner binary starts a container for each job:

```bash
# /usr/local/bin/ephemeral-runner-hook.sh
# Configured as a pre/post job hook via ACTIONS_RUNNER_HOOK_JOB_STARTED
#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="runner-job-${GITHUB_RUN_ID}-${GITHUB_JOB}"
WORKSPACE="/path/to/project

docker run -d \
  --name "$CONTAINER_NAME" \
  --rm \
  --network host \
  --security-opt seccomp=unconfined \
  -v /path/to/project \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /path/to/project \
  -e GITHUB_ACTIONS=true \
  -e RUNNER_TEMP=/path/to/project \
  ghcr.io/example-org/example-repo:ubuntu-24.04 \
  tail -f /dev/null
```

Custom runner image `Dockerfile`:

```dockerfile
# docker/runner.Dockerfile
FROM ubuntu:24.04

ARG NODE_VERSION=22
ARG PNPM_VERSION=9

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg lsb-release \
    build-essential python3 python3-pip \
    libssl-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Node.js via NodeSource
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && corepack enable \
    && corepack prepare pnpm@${PNPM_VERSION} --activate

# Wrangler (pinned version for reproducibility)
RUN npm install -g wrangler@3.x --no-save

# Playwright system dependencies
RUN npx playwright install-deps chromium

# GitHub runner user
RUN useradd -m -s /bin/bash runner
USER runner
WORKDIR /home/runner
```

## Systemd Unit for Multi-Runner Instances

A single bare-metal host can run multiple concurrent runner instances, each with an isolated workspace, using a parameterized systemd template:

```ini
# /etc/systemd/system/github-runner@.service
[Unit]
Description=GitHub Actions Runner — instance %i
After=network-online.target docker.service
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=github-runner
Group=github-runner
WorkingDirectory=/path/to/project
Environment=RUNNER_ALLOW_RUNASROOT=0
Environment=DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1
ExecStartPre=/usr/local/bin/ensure-runner-registered %i
ExecStart=/path/to/project
ExecStop=/bin/kill -SIGTERM $MAINPID
Restart=always
RestartSec=10s
KillMode=process
TimeoutStopSec=30

# Resource limits per runner instance
CPUQuota=400%          # 4 cores per instance on an 8-core host
MemoryMax=12G
TasksMax=4096

[Install]
WantedBy=multi-user.target
```

```bash
# Enable 3 concurrent runner instances on one host
for i in 1 2 3; do
  sudo systemctl enable github-runner@$i
  sudo systemctl start  github-runner@$i
done

# Check all instances
sudo systemctl status 'github-runner@*'
```

## Runner Registration and Token Rotation via GitHub API

```bash
#!/usr/bin/env bash
# scripts/register-runner.sh — called by Ansible or manually
set -euo pipefail

ORG="ORCHORDS"
REPO="example project"
RUNNER_NAME="${1:-$(hostname)}"
RUNNER_LABELS="${2:-bare-metal,linux,x64}"
GH_PAT="${GITHUB_PAT}"  # PAT with manage_runners:org scope

# Fetch a registration token (expires in 1 hour)
TOKEN=$(curl -s -X POST \
  -H "Authorization: Bearer ${GH_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${ORG}/${REPO}/actions/runners/registration-token" \
  | jq -r '.token')

/path/to/project \
  --url "https://github.com/${ORG}/${REPO}" \
  --token "$TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --runnergroup "bare-metal-prod" \
  --work "_work" \
  --replace \
  --unattended

echo "Runner ${RUNNER_NAME} registered successfully"
```

Remove a deregistered or stale runner:

```bash
REMOVE_TOKEN=$(curl -s -X POST \
  -H "Authorization: Bearer ${GITHUB_PAT}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/example-org/example-repo \
  | jq -r '.token')

./config.sh remove --token "$REMOVE_TOKEN" --unattended
```

## Monitoring Fleet Health with Prometheus

```yaml
# prometheus/runner-fleet-alerts.yml
groups:
  - name: github-runner-fleet
    rules:
      - alert: RunnerInstanceDown
        expr: up{job="github-runner"} == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Runner {{ $labels.instance }} is unreachable"

      - alert: RunnerDiskFull
        expr: |
          (node_filesystem_avail_bytes{mountpoint="/home",job="node-exporter"}
           / node_filesystem_size_bytes{mountpoint="/home"}) < 0.10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Runner {{ $labels.instance }} disk below 10%"

      - alert: RunnerHighMemoryPressure
        expr: |
          node_memory_MemAvailable_bytes{job="node-exporter"} < 2147483648
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Runner {{ $labels.instance }} memory below 2 GB available"
```

Node exporter scrape config for runner hosts:

```yaml
# prometheus/scrape-configs/runners.yml
- job_name: node-exporter
  static_configs:
    - targets:
        - runner-01.bare.example project.example.com:9100
        - runner-02.bare.example project.example.com:9100
        - runner-03.bare.example project.example.com:9100
  relabel_configs:
    - source_labels: [__address__]
      target_label: instance
```

## pnpm Store Caching on Local NVMe

```bash
# On the runner host — configure pnpm to use a shared store on NVMe
sudo -u github-runner pnpm config set store-dir /path/to/project

# Bind-mount the store into ephemeral Docker runner containers (see above)
# -v /path/to/project

# Periodic store prune to prevent unbounded growth
# /etc/cron.weekly/pnpm-store-prune
#!/usr/bin/env bash
sudo -u github-runner pnpm store prune
```

## OS Patching Without Disrupting Active Jobs

```bash
# /usr/local/bin/runner-safe-update.sh
#!/usr/bin/env bash
# Drain: wait for active jobs to finish before patching

API_BASE="https://api.github.com/repos/example-org/example-repo

# Find this runner's ID
RUNNER_ID=$(curl -s -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  "${API_BASE}" | jq --arg name "$(hostname)" \
  '.runners[] | select(.name == $name) | .id')

# Mark runner as offline/drain
curl -s -X DELETE \
  -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  "${API_BASE}/${RUNNER_ID}"

# Wait for running systemd units to stop (max 30 min)
timeout 1800 bash -c \
  'until ! systemctl --quiet is-active "github-runner@*"; do sleep 30; done'

# Apply OS patches
sudo apt-get update && sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Reboot if kernel was updated
needs-restarting -r || sudo reboot
```

## Mobile vs Desktop Considerations

The example project build fleet splits by target:

- **Linux bare metal (this article)**: Workers bundles, Next.js builds, Docker image pushes, Playwright E2E, pnpm unit tests. No GPU required. Fastest builds due to NVMe local cache and no container orchestration overhead.
- **macOS Mac minis (separate fleet)**: React Native iOS/macOS builds via Expo EAS self-hosted or Fastlane. macOS runners are not ephemeral-containerized (no Docker-in-Docker); workspace cleanup is handled by a pre-job script that removes the previous run's `node_modules` and build outputs.
- **Shared concern**: Both fleets use the same Ansible roles for runner registration, the same Prometheus/Alertmanager config for health monitoring, and the same `scripts/register-runner.sh` for token rotation.

## Anti-patterns

- Running the GitHub runner binary as root (`RUNNER_ALLOW_RUNASROOT=1`) — creates security risk; use a dedicated `github-runner` user with sudo only for specific commands via `/etc/sudoers.d/github-runner`
- Persisting `node_modules` or build artifacts in the runner workspace across jobs — use ephemeral Docker containers or `rm -rf $GITHUB_WORKSPACE` in a pre-job hook
- Sharing a single runner registration token across multiple hosts — each host should have its own registration; a revoked token takes down all runners sharing it
- Configuring unlimited `CPUQuota` and `MemoryMax` per instance — a runaway job can OOM the host, killing other runner instances; always set cgroup resource limits
- Skipping OS patching because "runners are ephemeral" — the host OS is not ephemeral; unpatched kernel vulnerabilities in the Docker daemon affect all containers on the host

## Gotchas

- GitHub runner registration tokens expire after 1 hour; the Ansible registration step must be run immediately after fetching the token, not at playbook schedule time
- Runner software auto-updates by default; pin the version in Ansible and set `DISABLE_AUTO_UPDATE=1` in the systemd unit environment to prevent mid-fleet version skew during a deployment
- The GitHub API `DELETE /runners/:id` endpoint only removes the runner record; the systemd service keeps running and the runner reconnects with a new ID on next start — follow with `./config.sh remove` to fully deregister
- Docker build jobs running inside ephemeral containers with `-v /var/run/docker.sock` have full host Docker daemon access; scope with rootless Docker or `--security-opt no-new-privileges` for untrusted workflows
- Disk cleanup for Docker dangling images and unused volumes must be scheduled explicitly: `docker system prune -af --volumes` weekly via cron, otherwise NVMe fills up within days of heavy image-build workloads

## Verification

```bash
# List all registered runners and their status
curl -s -H "Authorization: Bearer $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/example-org/example-repo \
  | jq '.runners[] | {name: .name, status: .status, busy: .busy, labels: [.labels[].name]}'

# Check systemd runner instance health on a host
sudo systemctl status 'github-runner@*'

# Trigger a test workflow on a specific runner label
gh workflow run ci.yml --ref main -f runner=bare-metal

# Monitor a runner's resource usage during a build
watch -n 2 'systemctl status github-runner@1 | grep -E "CPU|Memory|Main PID"'

# Verify pnpm store is on NVMe (not tmpfs)
df -h /path/to/project
```

## Related

- `documentation/docs/policies/infra/arc-github-runners-k8s.md`
- `documentation/docs/policies/infra/github-self-hosted-runners.md`
- `documentation/docs/policies/infra/self-hosted-runner-queue-stuck.md`
- `documentation/docs/policies/infra/cloudflare-tunnel-private-services.md`
- `documentation/docs/policies/infra/systemd-service-hardening.md`
- `documentation/docs/policies/infra/unattended-upgrades-os-patching.md`

## Sources

- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/about-self-hosted-runners
- https://docs.github.com/en/rest/actions/self-hosted-runners
- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/autoscaling-with-self-hosted-runners
- https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/running-scripts-before-or-after-a-job
- https://www.freedesktop.org/software/systemd/man/systemd.resource-control.html
