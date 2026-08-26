# Git Scalar large-repository enlistment governance

**Issue:** Large repositories need coordinated partial-clone, sparse-checkout, configuration, and maintenance choices rather than unrelated local tweaks.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Scalar is Git's opinionated large-repository management tool. It manages enlistments, performance configuration, background maintenance, reconfiguration, diagnostics, and deletion. Adopt it only after benchmarking the repository and validating its sparse layout and tool compatibility.

## Controls and verification

- Pin Git across every enlistment reader.
- Record which settings Scalar owns.
- Reconfigure after upgrades in a canary first.
- Treat diagnostic archives as potentially sensitive.
- Test IDE, hooks, build, and repository-wide checks under the selected checkout.
- Benchmark clean clone, fetch, status, build, and full-check workflows; test unregister/delete recovery.

## Sources

- [Git: scalar](https://git-scm.com/docs/scalar)
- [Git: partial clone](https://git-scm.com/docs/partial-clone)
