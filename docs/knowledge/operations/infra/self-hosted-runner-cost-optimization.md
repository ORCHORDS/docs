# Self-Hosted Runner Cost Optimization for CI

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A growing monorepo triggers CI on every pull request, running test suites and
Workers builds on GitHub-hosted runners. The bill reaches $2,000–$8,000/month
for larger teams. Switching to self-hosted runners cuts marginal compute cost
to near zero but introduces idle-time waste, cold-start latency, and fleet
management overhead. This article covers the full cost-optimization lifecycle
from fleet sizing through cache warm-up to auto-scaling policies.

## Context

GitHub Actions runner pricing (2026):
- GitHub-hosted `ubuntu-latest` (2 vCPU, 7 GB): $0.008/minute
- GitHub-hosted `ubuntu-latest-4-core`: $0.016/minute
- GitHub-hosted macOS: $0.08–$0.12/minute
- Self-hosted (EC2 / bare metal): cost of compute only, GitHub charges $0

Breakeven for self-hosted vs GitHub-hosted (`ubuntu-latest`):

| Monthly CI minutes | GitHub cost | EC2 c7g.xlarge (4 vCPU) on-demand | Break-even |
|---------------------|-------------|-------------------------------------|------------|
| 10,000 | $80 | $135 (always-on) | No |
| 50,000 | $400 | $135 (always-on) | Yes if utilization >33% |
| 200,000 | $1,600 | $270 (2 instances) | Yes at any utilization |

The key levers:
1. **Right-size instances** to match actual CI workloads
2. **Auto-scale to zero** when no jobs are queued
3. **Maximize cache hit rate** to reduce job duration
4. **Parallelize with job sharding** to reduce wall-clock time (and idle minutes)
5. **Use spot/preemptible instances** for non-blocking CI stages

---

## Section 1: Auto-Scaling to Zero with ARC (Actions Runner Controller)

ARC scales Kubernetes-hosted runner pods from 0 to N based on the GitHub
webhook job queue, then scales back to 0 when idle. Zero idle cost.

```yaml
# k8s/arc/scale-set-config.yaml
apiVersion: actions.github.com/v1alpha1
kind: AutoscalingRunnerSet
metadata:
  name: workers-ci-runners
  namespace: arc-systems
spec:
  githubConfigUrl: "https://github.com/myorg/myrepo"
  githubConfigSecret: arc-github-secret

  minRunners: 0       # ← scale to zero when idle
  maxRunners: 20      # ← cap to control cloud cost

  template:
    spec:
      containers:
        - name: runner
          image: ghcr.io/actions/actions-runner:latest
          resources:
            requests:
              cpu: "2"
              memory: "4Gi"
            limits:
              cpu: "4"
              memory: "8Gi"
          volumeMounts:
            - name: work
              mountPath: /path/to/project
            - name: npm-cache
              mountPath: /path/to/project
      volumes:
        - name: work
          emptyDir: {}
        - name: npm-cache
          persistentVolumeClaim:
            claimName: npm-cache-pvc  # shared PVC for cache warmth
```

For AWS-native auto-scaling without Kubernetes, use `actions-runner-controller`
with the Karpenter node provisioner to launch spot EC2 instances on demand:

```yaml
# karpenter/nodepool-ci.yaml
apiVersion: karpenter.sh/v1beta1
kind: NodePool
metadata:
  name: ci-runners
spec:
  template:
    spec:
      nodeClassRef:
        apiVersion: karpenter.k8s.aws/v1beta1
        kind: EC2NodeClass
        name: ci-runner
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]  # prefer spot
        - key: node.kubernetes.io/instance-type
          operator: In
          values: ["c7g.xlarge", "c7g.2xlarge", "c6g.xlarge"]
  limits:
    cpu: 160          # 40 × c7g.xlarge = $40/hr max spot burst
  disruption:
    consolidationPolicy: WhenEmpty
    consolidateAfter: 60s   # terminate idle nodes after 60s
```

---

## Section 2: Caching Strategies to Reduce Job Duration

Reducing job duration is equivalent to reducing compute spend. Targets:
- `pnpm install` or `npm ci`: from 60–90s to <5s via cache
- TypeScript build: from 30–60s to <10s via incremental compilation cache
- Wrangler bundle: from 20–40s to <5s via esbuild cache

```yaml
# .github/workflows/workers-ci.yml
name: Workers CI
on: [push, pull_request]

jobs:
  build-test:
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # needed for changeset detection

      # Layer 1: pnpm store cache (content-addressable, very high hit rate)
      - name: Cache pnpm store
        uses: actions/cache@v4
        id: pnpm-cache
        with:
          path: ~/.local/share/pnpm/store
          key: pnpm-${{ runner.os }}-${{ hashFiles('**/pnpm-lock.yaml') }}
          restore-keys: pnpm-${{ runner.os }}-

      - uses: pnpm/action-setup@v4
        with:
          run_install: false

      - name: Install deps (pnpm)
        run: pnpm install --frozen-lockfile --prefer-offline

      # Layer 2: TypeScript incremental cache
      - name: Cache TS build info
        uses: actions/cache@v4
        with:
          path: |
            **/tsconfig.tsbuildinfo
            **/.tsbuildinfo
          key: tsbuild-${{ runner.os }}-${{ hashFiles('**/tsconfig*.json', 'src/**/*.ts') }}
          restore-keys: tsbuild-${{ runner.os }}-

      # Layer 3: esbuild / Wrangler bundle cache
      - name: Cache wrangler bundle
        uses: actions/cache@v4
        with:
          path: .wrangler/
          key: wrangler-${{ runner.os }}-${{ hashFiles('src/**', 'wrangler.toml') }}
          restore-keys: wrangler-${{ runner.os }}-

      - name: Build and test
        run: |
          pnpm run typecheck
          pnpm run test
          pnpm exec wrangler deploy --dry-run --outdir dist/
```

On self-hosted runners, mount `/path/to/project as a
persisted volume (EFS, NFS, or local SSD with node affinity) rather than
relying on GitHub's managed cache, which adds latency for cache restore:

```bash
# Benchmark: managed cache restore vs local pnpm store
# Managed cache restore: 15–25s for a 300 MB pnpm store
# Local EFS volume mount: 0.2s (already mounted)
# Local NVMe SSD (node affinity): 0.1s
```

---

## Section 3: Job Sharding and Changeset-Based Skipping

For monorepos, the biggest cost reduction is not running CI at all for
packages that haven't changed.

```yaml
# .github/workflows/affected-matrix.yml
name: Affected CI Matrix
on:
  pull_request:

jobs:
  detect-changes:
    runs-on: self-hosted
    outputs:
      workers: ${{ steps.nx.outputs.affected-workers }}
      services: ${{ steps.nx.outputs.affected-services }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Detect affected projects (Nx)
        id: nx
        run: |
          AFFECTED=$(pnpm exec nx show projects --affected --base=origin/main --json)
          WORKERS=$(echo "$AFFECTED" | jq '[.[] | select(startswith("worker-"))]')
          SERVICES=$(echo "$AFFECTED" | jq '[.[] | select(startswith("service-"))]')
          echo "affected-workers=$WORKERS" >> "$GITHUB_OUTPUT"
          echo "affected-services=$SERVICES" >> "$GITHUB_OUTPUT"

  test-workers:
    needs: detect-changes
    if: ${{ needs.detect-changes.outputs.workers != '[]' }}
    strategy:
      matrix:
        worker: ${{ fromJson(needs.detect-changes.outputs.workers) }}
      max-parallel: 8   # shard across 8 runners simultaneously
    runs-on: self-hosted
    steps:
      - uses: actions/checkout@v4
      - name: Test ${{ matrix.worker }}
        run: pnpm exec nx test ${{ matrix.worker }} --passWithNoTests
```

For Turborepo:

```yaml
- name: Run affected via Turborepo
  run: |
    pnpm exec turbo run build test lint \
      --filter="...[origin/main]" \
      --cache-dir=.turbo \
      --concurrency=4
  env:
    TURBO_TOKEN: ${{ secrets.TURBO_TOKEN }}
    TURBO_TEAM: ${{ secrets.TURBO_TEAM }}
```

Turbo remote cache (Turborepo Cloud or self-hosted via `ducktape` / Depot):
- Build cache hit: skips the task entirely (zero CPU time)
- For Workers: a cache hit on `wrangler bundle` reduces a 40s step to <1s

---

## Anti-patterns

- **Always-on large instances**: running c7g.4xlarge 24/7 for a team that uses CI
  8 hours/day burns 66% idle compute. Auto-scale to zero during nights/weekends.
- **Single large runner per job**: a 16-vCPU instance running a test suite
  single-threaded wastes 15 cores. Shard tests across multiple smaller runners
  for better parallelism and same or lower total cost.
- **No cache versioning**: when `package.json` changes, the old pnpm cache key
  still matches but is invalid. Always include a lockfile hash in the cache key.
- **Self-hosted for macOS without justification**: macOS spot instances (EC2 Mac)
  have a 24-hour minimum billing window (dedicated host requirement). They are
  economical only if utilization exceeds 4 hours/day on that host.
- **Storing build artifacts in GitHub Actions cache**: the 10 GB cache limit per
  repo causes evictions. Large artifacts (Docker images, compiled binaries) belong
  in R2, S3, or a container registry, not the cache.
- **Over-parallelizing on spot instances**: spot interruptions during matrix jobs
  leave orphaned job legs. Always set `continue-on-error: false` for leaf jobs
  and handle spot termination with a 2-minute grace period hook.

---

## Gotchas

- GitHub Actions ephemeral runners (JIT tokens) expire 1 hour after registration.
  If a queued job waits >1 hour for a spot instance to come up, the runner token
  is invalid and the job never starts. Set a maximum queue wait or use on-demand
  fallback.
- `actions/cache` with `restore-keys` can restore a stale cache from a different
  branch, causing non-deterministic builds. Use exact-match keys for strict
  reproducibility; use `restore-keys` only for best-effort warm-starts.
- ARC runners running in Kubernetes pods inherit the node's instance lifecycle.
  A Karpenter consolidation that terminates a node mid-job cancels the running
  job without retry. Set `karpenter.sh/do-not-disrupt: "true"` on runner pods.
- Self-hosted runners on AWS do not automatically have access to private ECR.
  Attach an instance profile with `ecr:GetAuthorizationToken` and
  `ecr:BatchGetImage` permissions.
- Turbo remote cache requires content-addressed caching to be deterministic.
  Timestamps embedded in build outputs (some frameworks add them) break cache
  hits. Audit build outputs for embedded `Date.now()` or `new Date()` calls.

---

## Verification

```bash
# Calculate current GitHub Actions spend
gh api /repos/myorg/myrepo/actions/billing | jq .

# List workflow run durations for cost analysis
gh run list --repo myorg/myrepo --limit 100 --json durationMs,name,status | \
  jq 'group_by(.name) | map({name: .[0].name, avg_ms: (map(.durationMs) | add / length)}) | sort_by(.avg_ms) | reverse'

# Verify ARC runner scale-from-zero
kubectl get pods -n arc-systems -w   # watch pods appear when jobs queue

# Check cache hit rates in workflow logs
gh run view <RUN_ID> --log | grep -E "Cache (Hit|Miss|Restored)"

# Confirm spot interruption handling
aws ec2 describe-spot-instance-requests \
  --filters "Name=state,Values=closed" \
  --query 'SpotInstanceRequests[].StatusMessage' --output text | \
  grep -c "interrupted"  # should be low relative to total completions
```

Expected: <5% spot interruption rate, >80% cache hit rate on pnpm installs,
no jobs waiting >5 minutes for a runner when ARC is configured.

---

## Related

- `/documentation/docs/policies/infra/github-self-hosted-runners.md`
- `/documentation/docs/policies/infra/github-runner-bare-metal-fleet.md`
- `/documentation/docs/policies/infra/arc-github-runners-k8s.md`
- `/documentation/docs/policies/infra/karpenter-keda-autoscaling.md`
- `/documentation/docs/policies/infra/pnpm-docker-multistage-ci.md`

---

## Sources

- GitHub Actions billing: https://docs.github.com/en/billing/managing-billing-for-github-actions
- Actions Runner Controller (ARC): https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners-with-actions-runner-controller
- Karpenter disruption controls: https://karpenter.sh/docs/concepts/disruption/
- Turborepo remote caching: https://turbo.build/repo/docs/core-concepts/remote-caching
- AWS EC2 Mac dedicated hosts: https://aws.amazon.com/ec2/instance-types/mac/
- Nx affected commands: https://nx.dev/ci/features/affected
