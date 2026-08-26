# Git Maintenance: Scheduled Background Pack Optimization

- Date: 2026-08-22
- Author: example.com
- Status: production

## Keeping Large Repositories Fast Without Manual Intervention

Git repositories accumulate loose objects, fragmented pack files, stale remote-tracking refs, and an out-of-date commit-graph every day. Left unmanaged, `git fetch`, `git log`, and `git status` all degrade. `git gc` is the traditional remedy but it runs synchronously, blocks the terminal, and is blunt: it does everything or nothing.

`git maintenance` (introduced in Git 2.30) replaces ad-hoc `git gc` calls with a suite of focused, incremental tasks that can be scheduled to run in the background. Each task targets one bottleneck: `prefetch` keeps the object database warm, `gc` compacts objects, `commit-graph` builds the reachability index, `loose-objects` packs ephemeral blobs, and `pack-refs` consolidates reference files.

In CI environments where runners are ephemeral, scheduling works differently than on developer machines: you pre-warm a cached clone (stored in the runner's object cache or a shared NFS mount) and run maintenance at the end of each job so the next job inherits a compact repository.

## Context

Stack: GitHub Actions, self-hosted runners on AWS EC2 with an EFS mount shared across runner instances, Node 22 monorepo. The shared EFS clone is used as a reference for `git clone --reference` to speed up fresh checkouts.

## Task Reference

```bash
# Run a single maintenance task manually
git maintenance run --task=commit-graph
git maintenance run --task=prefetch
git maintenance run --task=loose-objects
git maintenance run --task=pack-refs
git maintenance run --task=gc

# Run all tasks in the recommended order
git maintenance run --auto

# Register a repository for background scheduling (writes to ~/.gitconfig)
git maintenance start

# View registered repositories
git config --global --list | grep maintenance

# Deregister
git maintenance stop

# View the auto-scheduling thresholds (per-repo config)
git config --list | grep maintenance
```

The task execution order matters: run `commit-graph` after `gc` so the graph reflects the freshly compacted pack layout.

## Configuring Tasks and Schedules

```bash
# Tune loose-objects: pack when more than 100 loose objects exist
git config maintenance.loose-objects.auto 100

# Tune commit-graph: update after every fetch automatically
git config maintenance.commit-graph.auto 1

# Tune gc: disable automatic full gc (we run it on schedule instead)
git config maintenance.gc.auto 0

# Set prefetch schedule: hourly
git config maintenance.prefetch.schedule hourly

# Set commit-graph schedule: hourly
git config maintenance.commit-graph.schedule hourly

# Set loose-objects schedule: daily
git config maintenance.loose-objects.schedule daily

# Set pack-refs schedule: weekly
git config maintenance.pack-refs.schedule weekly

# Set gc schedule: weekly (full repack is expensive)
git config maintenance.gc.schedule weekly
```

On Linux, `git maintenance start` writes systemd timer units to `~/.config/systemd/user/`. On macOS it writes launchd plists. On CI runners that lack a persistent daemon, use the cron approach below instead.

## CI Runner Pre-Warm Pattern

```yaml
# .github/workflows/ci-reference-maintenance.yml
# Runs on a schedule to keep the shared EFS reference clone compact.
name: Maintain Reference Clone

on:
  schedule:
    # Run at 02:00 UTC every day
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  maintain:
    runs-on: [self-hosted, linux, x64]
    timeout-minutes: 30

    steps:
      - name: Fetch latest objects into reference clone
        run: |
          REPO=/mnt/efs/git-reference/monorepo.git
          cd "$REPO"
          # Bare clone — use fetch, not maintenance prefetch
          git fetch --all --prune --prune-tags

      - name: Run maintenance tasks in order
        run: |
          REPO=/mnt/efs/git-reference/monorepo.git
          cd "$REPO"

          echo "=== loose-objects ==="
          git maintenance run --task=loose-objects

          echo "=== pack-refs ==="
          git maintenance run --task=pack-refs

          echo "=== commit-graph ==="
          git maintenance run --task=commit-graph

          echo "=== gc (weekly only) ==="
          DAY=$(date +%u)  # 1=Mon ... 7=Sun
          if [[ "$DAY" == "7" ]]; then
            git maintenance run --task=gc
            # Rebuild commit-graph after repack
            git maintenance run --task=commit-graph
          fi

      - name: Report pack statistics
        run: |
          REPO=/mnt/efs/git-reference/monorepo.git
          cd "$REPO"
          git count-objects -vH
          git for-each-ref --format='%(refname)' refs/ | wc -l
```

## Performance Impact Measurement

Measure the real cost of each task and the benefit to downstream operations before committing to a schedule.

```bash
#!/usr/bin/env bash
# scripts/measure-maintenance.sh
# Run this in the repository you want to profile.

set -euo pipefail

REPO="${1:-.}"
cd "$REPO"

header() { echo; echo "=== $* ==="; }

header "Baseline object stats"
git count-objects -vH

header "Time git log --oneline -1000 (before)"
time git log --oneline -1000 > /dev/null

header "Run loose-objects"
time git maintenance run --task=loose-objects

header "Run commit-graph"
time git maintenance run --task=commit-graph

header "Time git log --oneline -1000 (after commit-graph)"
time git log --oneline -1000 > /dev/null

header "Run pack-refs"
time git maintenance run --task=pack-refs

header "Time git for-each-ref (after pack-refs)"
time git for-each-ref > /dev/null

header "Post-maintenance object stats"
git count-objects -vH

header "Commit-graph info"
git commit-graph verify --reachable 2>&1 | head -5
```

Typical improvements on a 2-year-old monorepo with 50 k commits:

| Operation | Before | After commit-graph |
|---|---|---|
| `git log --ancestry-path A..B` | 4.2 s | 0.3 s |
| `git merge-base A B` | 1.8 s | 0.05 s |
| `git branch --merged` | 3.1 s | 0.2 s |

## Anti-patterns

- Running `git gc` inside a hot CI path: full repack can take minutes and blocks the job
- Calling `git maintenance start` on ephemeral CI runners: the systemd/launchd timer is written to the runner's home dir and disappears with the instance
- Skipping `commit-graph` after `gc`: a freshly compacted pack without a matching commit-graph leaves traversal performance unimproved
- Setting `maintenance.gc.schedule=hourly`: full gc is I/O heavy; weekly is appropriate for active monorepos
- Not pruning stale remote refs before maintenance: loose objects from deleted remote branches will be repacked needlessly

## Gotchas

- `git maintenance run --task=gc` honours `gc.bigPackThreshold` and may skip repacking if the largest pack is below the threshold; verify with `git count-objects -vH`
- On NFS mounts, file-locking during pack-refs can conflict if two runners run maintenance simultaneously; add a file lock wrapper or stagger schedules
- The `prefetch` task requires a non-bare repository with configured remotes; bare repos (reference clones) must use `git fetch` directly
- `git maintenance start` writes to `~/.gitconfig`, not the repo's `.git/config`; global registration persists across worktrees but not across users or containers
- After `--split` commit-graph generation, the chain must be merged periodically with `git commit-graph write --reachable --split=replace` or the chain grows unboundedly

## Verification

```bash
# Confirm commit-graph exists and is valid
git commit-graph verify --reachable

# Count objects before and after
git count-objects -vH

# Confirm pack-refs consolidated refs
ls -1 .git/refs/remotes/ | wc -l  # should approach 0 after pack-refs

# Time a representative traversal
time git log --oneline --ancestry-path main~500..main > /dev/null
```

## Related

- [git-commit-graph-incremental-performance.md](git-commit-graph-incremental-performance.md)
- [git-cleanup-2026.md](git-cleanup-2026.md)
- [ci-cd-pipeline-2026.md](ci-cd-pipeline-2026.md)
- [monorepo-affected-builds-2026.md](monorepo-affected-builds-2026.md)
- [git-lfs-2026.md](git-lfs-2026.md)

## Sources

- https://git-scm.com/docs/git-maintenance
- https://git-scm.com/docs/git-commit-graph
- https://github.blog/engineering/infrastructure/scaling-git-database-at-github/
- Git 2.30 release notes
