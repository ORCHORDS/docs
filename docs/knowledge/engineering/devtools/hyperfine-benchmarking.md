# hyperfine-benchmarking

**Issue:** Comparing command performance requires manual timing and averaging
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Is ripgrep actually faster than grep for this codebase? Manual timing is imprecise.

## Pattern / Solution
hyperfine 'grep -r pattern .' 'rg pattern' runs both commands multiple times, discards warmup runs, and shows statistical comparison with mean, stddev, and relative speedup. Export results: --export-markdown results.md. Control runs: --runs 20.

## Gotchas
- Warmup runs fill OS file cache — benchmark hot path, not cold start, unless you need cold start
- --prepare with cache drop command for cold-cache benchmarks on Linux

## Related
- ripgrep-patterns, fd-find-patterns
