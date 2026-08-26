# self-hosted-runners-docker-official-image

**Issue:** Migrating GitHub Actions self-hosted runners from a rented netcup server to a home Lenovo laptop (WSL2 + Docker Desktop), keeping or improving CI speed without losing checks.
**Date:** 2026-08-23
**Author:** ORCHORDS
**Status:** deployed & verified

## Architecture (final)

```
Lenovo laptop (Win11, 16c/22GB WSL2 VM, mirrored networking)
  Docker Desktop (WSL integration w/ Ubuntu)
    ghcr.io/actions/actions-runner:latest  ← OFFICIAL image (multi-arch: linux amd64/arm64, macOS variants)
      ├─ orchords-node-runner:22   (official + Node 22 + corepack/pnpm)  → example project ×6, example project-site ×2, example.com ×2
      ├─ orchords-swift-runner:6.0.3 (official + Swift 6.0.3 + libncurses/libxml2 deps) → example project (removed for now)
      └─ orchords-example project-runner:android (official + JDK21, Gradle 9.6.1, Kotlin 2.4.10, Node 24, Android SDK36/bt37/NDK27.3 — per actions/runner-images macOS-26 manifest) → example project next week
Volumes: runnerwork-<repo><idx>:/_work (uid 1001), pnpm-store:/pnpm (shared)
```

## Results (measured, warm caches, parallel runners)

| Workflow | netcup | laptop | speedup |
|---|---|---|---|
| ci | 272s | 89–92s | ~3x |
| ci-preflight | 155s | 28–37s | ~4–5x |
| gitleaks | 181s | 17–36s | ~5–10x |
| deploy-web | 247s | 14s | ~17x |
| action-pin-guard | 293s | 15s | ~20x |
| example project swift tests | blocked (budget) | 19–21s | ∞ |

Key wins: parallel jobs (N runner containers per repo → jobs concurrent), persistent SwiftPM `--scratch-path` cache (10min cold build → 21s warm), shared pnpm store volume, migrated netcup-era caches (`_work/_tool` 203M + pnpm 245M) so first runs weren't cold.

## Confirmed pitfalls (each cost hours — don't repeat)

1. **Broker flap (`SocketException (125)`, runner offline every ~60–90s)** = upstream GitHub bug actions/runner#3899 (multiple reporters, latest runner version, different networks). Not fixable client-side. Mitigation: keep jobs short via warm caches; Docker restart policy reconnects cleanly.
2. **Official actions-runner image has NO entrypoint** — must run `config.sh --unattended --replace --name --url --token --labels --work /_work` then `run.sh` yourself (see ARC startup.sh contract; our `/opt/official-runners/start.sh`).
3. **Registration tokens expire after 1h** — a container restart loop with `404 Not Found` = stale token, fetch new `registration-token` and recreate.
4. **Work volumes must be uid 1001** — `System.UnauthorizedAccessException: /_work/_tool denied` otherwise. Fix: `docker run --rm --user root -v $vol:/w <local-image> chown -R 1001:1001 /w` (use a LOCAL image — pulling alpine over SSH hits the desktop credential helper).
5. **`wsl --shutdown` kills Docker Desktop** + its VM (all containers stop, images can vanish) + pops a GUI error. Recovery: `wsl -d Ubuntu -- true`, relaunch Docker Desktop via scheduled task (Start-Process over SSH session-0 fails), `docker start $(docker ps -aq)`. Set Docker Desktop AutoStart to reduce this.
6. **Docker CLI over SSH + `credsStore: desktop`** = "A specified logon session does not exist". Fix: `/root/.docker/config.json` → `{}` inside WSL (integration keeps re-adding it after restarts — re-clear after each Docker Desktop restart).
7. **WSL2 idle VM shutdown** (microsoft/WSL #13033/#40363): fix = NAT (or mirrored) + `vmIdleTimeout=-1` + `autoMemoryReclaim=disabled` + persistent in-VM process (systemd `wsl-alive.service` with `sleep infinity`).
8. **Swift on bare official image** needs libncurses6, libxml2, libicu etc. — missing one = `swift: error while loading shared libraries`. Also Ubuntu 26.04 soname mismatches (libicu78 vs 74) fixed by extracting 24.04 debs.
9. **SwiftPM cache**: `swift build --scratch-path /path/to/project outside `_work` survives checkout/clean. Build converges across killed runs (155M → 182M → green).
10. **Concurrency cancel-in-progress quirk**: GitHub replaces head-sha runs with merge-ref runs ("Canceling since a higher priority waiting request for ci-refs/pull/N/merge exists") — normal, not a failure. Fresh-volume runners also fail `HEAD~1..HEAD` commitlint on synthetic merge commits until workspace has history.
11. **CodeQL on private repos**: license-blocked (verified live: analysis runs locally, SARIF upload rejected "Code scanning is not enabled"). Honest `if: false` placeholders on example project/example project-site; example.com has active workflow whose upload silently fails = false coverage.

## Sources
- actions/runner#3899 (broker exits), actions/runner-images (macOS-26 manifest = toolset list), microsoft/WSL#13033, #40363
- ghcr.io/actions/actions-runner (official container), actions/actions-runner-controller runner/startup.sh (env contract)

## Related
- `github-actions-self-hosted-runners-2026.md` · `infra/github-self-hosted-runners.md` · `ci-budget-exhaustion-migration.md`
