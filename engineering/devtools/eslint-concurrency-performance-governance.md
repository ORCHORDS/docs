# ESLint concurrency performance governance

**Issue**

ESLint worker concurrency can reduce lint time on large repositories but also multiplies memory use, initialization work, and cache contention.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Benchmark `--concurrency=off`, fixed worker counts, and `auto` on the actual runner class.
- Pin ESLint, plugins, configuration, and cache location.
- Keep one cache writer per cache file and cap workers below memory and CPU quotas.
- Treat lint results as invariant across concurrency modes.

## Verification

1. Compare findings and exit status across modes.
2. Measure wall time, CPU, peak RSS, and cache warm/cold behavior.
3. Run under constrained CI cgroups and detect OOM or worker failure.

## Gotchas

- More workers can be slower for small projects.
- Plugin initialization cost repeats in workers.
- Shared external state in custom rules can become nondeterministic.

## Official source

- [Official documentation](https://eslint.org/docs/latest/use/command-line-interface#--concurrency)
