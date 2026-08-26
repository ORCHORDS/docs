# github-self-hosted-runners

**Issue:** GitHub self-hosted runners — setup, performance, multi-user private repos
**Date:** 2026-08-09
**Status:** documented

## Symptom
GitHub-hosted runners are slow (5-10 min for a
complex CI). You have 50 private repos with 10
contributors. You want a runner that:
1. Boots fast (< 30s)
2. Caches between runs
3. Handles multiple users
4. Stays secure

## Root cause
**GitHub-hosted runners are shared + slow.** Use
self-hosted runners.

**Source:** GitHub docs:
https://docs.github.com/en/actions/hosting-your-own-runners

## The "self-hosted runner" concept

A self-hosted runner is a machine you control that
runs GitHub Actions jobs:
- **Faster:** Your hardware, your network
- **Cached:** Persistent state between runs
- **Customizable:** Any OS, any tool
- **Private:** No external access

The runner is yours.

## The "runner tier" pattern

For runner tiers:
- **Repository-level:** Single repo (free for private)
- **Organization-level:** All org repos
- **Enterprise-level:** All enterprise repos

For multiple people / private repos, **organization-level**
is the right answer.

## The "install" pattern

For installation:
```bash
# 1. Create a registration token (admin)
# 2. Download the runner
mkdir actions-runner && cd actions-runner
curl -o actions-runner-linux-x64-2.319.1.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-x64-2.319.1.tar.gz
tar xzf ./actions-runner-linux-x64-2.319.1.tar.gz

# 3. Configure
./config.sh --url https://github.com/yourorg --token <REGISTRATION_TOKEN>

# 4. Run as a service
sudo ./svc.sh install
sudo ./svc.sh start
```

The runner is installed.

## The "runner group" pattern

For runner groups (multiple machines):
```yaml
# .github/workflows/ci.yml
runs-on:
  group: fast-runners
  labels: self-hosted, linux, x64, gpu
```

The runner is selected by group + labels.

## The "ephemeral runner" pattern

For ephemeral (clean state every run):
```bash
./run.sh --ephemeral
# Or in K8s: each pod is a fresh runner
```

Ephemeral = no state, no cache.

For most CI, **ephemeral** is the right answer.

## The "speed tuning" pattern

For speed:
- **CPU:** More cores = parallel jobs
- **RAM:** More = bigger builds
- **Disk:** NVMe SSD, not HDD
- **Network:** Local registry + cache
- **OS:** Ubuntu LTS (fastest)
- **Docker:** Layer cache

```yaml
# Hardware recommendation
CPU: 16+ cores
RAM: 32+ GB
Disk: 1TB NVMe SSD
Network: 10 Gbps
OS: Ubuntu 22.04 LTS
```

Tune for speed.

## The "caching" pattern

For cache:
```yaml
- uses: actions/cache@v4
  with:
    path: |
      ~/.npm
      ~/.cache/pip
      node_modules
    key: ${{ runner.os }}-deps-${{ hashFiles('**/package-lock.json') }}
    restore-keys: |
      ${{ runner.os }}-deps-
```

The cache is restored.

## The "Docker layer cache" pattern

For Docker layer cache:
```yaml
- uses: actions/cache@v4
  with:
    path: /tmp/.buildx-cache
    key: ${{ runner.os }}-buildx-${{ github.sha }}
    restore-keys: |
      ${{ runner.os }}-buildx-
```

The Docker cache is persistent.

## The "Docker registry mirror" pattern

For Docker pulls, use a local mirror:
```yaml
- name: Configure Docker
  run: |
    mkdir -p /etc/docker
    echo '{"registry-mirrors":["https://your-mirror.example.com"]}' > /etc/docker/daemon.json
```

The Docker pulls are local.

## The "multi-user isolation" pattern

For multi-user isolation:
- **Docker:** Each job in a container
- **Namespaces:** Linux user namespaces
- **gVisor:** Sandbox
- **Firecracker:** MicroVM

```yaml
jobs:
  build:
    runs-on: self-hosted
    container:
      image: node:20
      options: --user 1000:1000
```

Each job is in a container.

## The "private repo" pattern

For private repos, GitHub-hosted runners
have a limit. Self-hosted runners:
- **Unlimited minutes:** For private repos
- **Per-repo:** Free
- **Per-org:** Free

For private repos, self-hosted = free + fast.

## The "Kubernetes runner" pattern

For K8s-based runners:
- **actions-runner-controller:** ARC (recommended)
- **Runner pods:** Scale 0 to N
- **Ephemeral:** Each job is a pod

```bash
# Install ARC
helm install arc oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```

The runner is on K8s.

**Source:** actions-runner-controller:
https://github.com/actions/actions-runner-controller

## The "ARC" pattern

For ARC (Actions Runner Controller):
```yaml
# gha-runner-scale-set.yaml
apiVersion: actions.github.com/v1alpha1
kind: RunnerSet
metadata:
  name: my-runner-set
spec:
  githubConfigUrl: https://github.com/yourorg
  githubConfigSecret: github-config-secret
  runners:
    - type: stateless
      replicas: 5
```

The runner scales automatically.

## The "GPU runner" pattern

For GPU jobs:
```yaml
runs-on: self-hosted
container:
  image: tensorflow/tensorflow:latest-gpu
  options: --gpus all
```

The GPU is exposed.

## The "runner security" pattern

For security:
- **Pin versions:** Avoid supply chain attacks
- **Use ephemeral:** No state
- **Network isolation:** No internet (where possible)
- **Secret scanning:** Pre + post run
- **Update OS:** Patch regularly

```bash
# Update the runner
cd actions-runner && ./run.sh --update
```

The runner is patched.

## The "ARM runner" pattern

For ARM (cheaper, faster for some):
```bash
# Download ARM
curl -o actions-runner-linux-arm64-2.319.1.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-linux-arm64-2.319.1.tar.gz
```

The runner is ARM.

**Use case:** AWS Graviton, Apple Silicon.

## The "monitoring" pattern

For monitoring:
- **Runner health:** In the GitHub UI
- **Job duration:** Per runner
- **Queue depth:** Backlog
- **CPU/RAM:** Per runner

```yaml
- name: Report metrics
  run: |
    curl -X POST https://metrics.example.com/runner \
      -d "duration=$JOB_DURATION&runner=$RUNNER_NAME"
```

The runner is monitored.

## The "auto-scaling" pattern

For auto-scaling, use ARC or custom:
- **Min:** 0 runners (scale to zero)
- **Max:** 100 runners
- **Queue-based:** More runners when backed up
- **Time-based:** More during work hours

```yaml
spec:
  runners:
    - type: stateless
      minRunners: 0
      maxRunners: 100
```

The runner auto-scales.

## The "runner cost" pattern

For cost:
- **GitHub-hosted:** Pay per minute
- **Self-hosted:** Pay for the machine
- **Hybrid:** Self-hosted for heavy, GitHub for burst

For private repos with steady load, **self-hosted** wins.

## The "self-hosted runner anti-pattern" anti-patterns

### 1. No ephemeral
- **Issue:** State leaks between jobs
- **Fix:** Ephemeral runners

### 2. No isolation
- **Issue:** Job A reads Job B's files
- **Fix:** Container per job

### 3. No caching
- **Issue:** Re-build every time
- **Fix:** Cache

### 4. No monitoring
- **Issue:** Stuck runners
- **Fix:** Metrics + alerts

### 5. Single runner
- **Issue:** Queue + single point of failure
- **Fix:** Multiple runners

### 6. No updates
- **Issue:** Old + vulnerable
- **Fix:** Update regularly

## Verification
- **Test:** Runner picks up jobs
- **Test:** Cache works
- **Test:** Ephemeral cleans up
- **Live:** Runner health monitored
- **Audit:** Quarterly security review

## Gotchas
- **The "no ephemeral" anti-pattern.** Use ephemeral.
- **The "no isolation" anti-pattern.** Container per job.
- **The "no caching" anti-pattern.** Cache.
- **The "no updates" anti-pattern.** Update regularly.

## Related
- `infra/secrets-rotation-runbook.md`
- `infra/pnpm-workspaces-monorepo.md`
- `infra/wrangler-deploys.md`
- `deploy/preview-environments.md`
- GitHub docs:
  https://docs.github.com/en/actions/hosting-your-own-runners
- ARC:
  https://github.com/actions/actions-runner-controller
- Actions runner: https://github.com/actions/runner
