> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `Benchmarks.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/BENCHMARKS.md` in the docs repo.

---
title: "benchmarks.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "lisa.martinez (QA Lead)"
status: "approved"
iso-refs: ["ISO/IEC 25010:2023 (Performance efficiency)"]
related-workflow: ".forgejo/workflows/benchmarks.yml"
---

# benchmarks.yml — Engine Benchmarks on PR

**Project:** Beetle Studio
**Owner:** Lisa Martinez (QA Lead) — benchmark suite; James Park (Graphics Engineer) — engine perf interpretation
**Reviewers:** Kirk Beka (CTO), Mike Johnson (DevOps)
**ISO Standards:** ISO/IEC 25010:2023 (Performance efficiency subcharacteristic)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/benchmarks.yml` (1,090 bytes, 1 job)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Build and run the `bench_runner` target when a PR touches `benchmarks/**` or `src/Engine/**` |
| **Diátaxis form** | Reference |
| **Primary audience** | Lisa Martinez, James Park |
| **Secondary audience** | All graphics engineers; release engineers reading perf trends |

---

## Purpose

Catches perf regressions on `src/Engine/**` before merge. Builds the `bench_runner` target from `benchmarks/CMakeLists.txt` (if it exists) and runs the Google Benchmark binary, printing results in console format. The job is **advisory** — it always exits 0 even on benchmark regression so that perf data is collected but does not block merge.

## Trigger

| Event | Filter |
|---|---|
| `pull_request` | `branches: [main]`, `paths: ['benchmarks/**', 'src/Engine/**']` |

## Concurrency

| Group | Behavior |
|---|---|
| `benchmarks-${{ github.event.pull_request.number }}` | `cancel-in-progress: true` — only the latest push on a PR runs |

## Jobs & Steps

### `benchmark`

| Step | Purpose | Notes |
|---|---|---|
| 1. Checkout | `actions/checkout@v4`, `fetch-depth: 1` | Shallow clone to save time |
| 2. Build and run benchmarks | If `benchmarks/CMakeLists.txt` exists, run `cmake -B build -DCMAKE_BUILD_TYPE=Release`, `cmake --build build --parallel $(nproc)`, then `./build/bench_runner --benchmark_format=console` | Job always exits 0 |

The step is wrapped in `set +e` and the final `exit 0` makes the workflow a no-op gating signal — it shows in the UI but does not block the PR.

## Configuration

### Secrets

None. The job does not call any external API.

### Environment variables

None explicit; uses the runner's default `${{ runner.* }}` and `${{ github.* }}` context.

### Tools (auto-installed by the step)

| Tool | Installed by |
|---|---|
| `cmake` | `apt-get install -y cmake g++` if not present |
| `g++` | same |
| Google Benchmark | expected to be declared as a target in `benchmarks/CMakeLists.txt`; no vcpkg fetch happens in the workflow |

## Reading the Output

Console format (Google Benchmark default):

```
--------------------------------------------------------------------
Benchmark                          Time             CPU   Iterations
--------------------------------------------------------------------
BM_DecodeFrame_1080p           1245323 ns      1245100 ns          562
BM_ColorConvert_RGBtoYUV      45623812 ns     45612300 ns           15
```

A regression of >10% on a per-PR basis is worth investigating. A regression of >50% should block merge. The thresholds are not currently enforced by the workflow; they live in `docs/PERFORMANCE_BENCHMARKS.md` (the historical results page) and are reviewed manually by Lisa Martinez.

## Known Limitations

- **Advisory only.** A PR that doubles the engine's decode time will still merge because the job exits 0. A future improvement: parse the JSON output (`--benchmark_format=json`) and `exit 1` when a registered baseline is exceeded by N%.
- **No baseline storage.** Each PR's run is ephemeral. The historical trends page (`docs/PERFORMANCE_BENCHMARKS.md`) is hand-curated.
- **No Windows runner.** Builds on `ubuntu-latest`, so the compile uses `g++` not `cl.exe`. If the engine is MSVC-specific, the build will fail silently. The branch is not gated.
- **Path filter is too narrow.** Touching `src/Audio/` or `src/Effects/` will not trigger the workflow, even if a new effect relies on the same decode path.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|
| Workflow does not run on a PR | Path filter excluded it | Verify the diff touches `benchmarks/**` or `src/Engine/**`; check the Actions tab filter |
| Build fails with "cmake: not found" | The apt-get install step failed silently | Check runner connectivity; pin to a newer ubuntu image |
| Benchmarks run but produce no output | `bench_runner` not built; missing target in `CMakeLists.txt` | Add the target; verify locally with `cmake --build build --target bench_runner` |
| Job times out at 10 minutes | Bench suite is too large | Increase `timeout-minutes`; or split into per-suite PR runs |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Performance Benchmarks History](../../PERFORMANCE_BENCHMARKS.md)
- [Test Strategy](../TEST_STRATEGY.md) — section "Performance / Regression Benchmarks"

### External

- Google Benchmark user guide — https://github.com/google/benchmark
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- ISO/IEC 25010:2023 — Performance efficiency subcharacteristic

---

*Grounded in: ISO/IEC 25010:2023 (Performance efficiency). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/benchmarks.yml`.*
