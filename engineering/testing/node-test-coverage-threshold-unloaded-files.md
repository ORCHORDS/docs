# Node test-runner coverage thresholds and unloaded files

**Issue:** A native Node.js coverage gate can report a high percentage while omitting source files that no test ever loaded.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin a Node.js version whose test-runner coverage CLI or `run()` API supports the required options. Set line, branch, and function thresholds independently, and define include/exclude globs from the deployable source boundary. Where supported, enable inclusion of never-loaded candidate files so they enter the report at zero coverage rather than disappearing from the denominator.

Keep generated code, vendored dependencies, migrations, and configuration exclusions narrow and reviewed. Emit LCOV for inspection in addition to the pass/fail threshold, but run a normal test reporter too because the LCOV reporter does not replace test results. Treat coverage as a missing-execution signal, not proof of assertions or correctness.

## Verification

Create one imported source file and one matching but never imported file; prove the second is counted at zero. Add uncovered branches and functions and require each threshold to fail independently. Test glob boundaries, source maps for the pinned version, child processes/workers used by the suite, no-tests behavior, and reporter destinations.

## Gotchas

- Coverage support and option stability vary by Node release.
- Excluding a path changes both numerator and denominator.
- Passing global thresholds can still hide a critical uncovered file.

## Official source

- [Node.js test runner coverage](https://nodejs.org/api/test.html#collecting-code-coverage)
