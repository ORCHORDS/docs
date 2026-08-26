# Git sparse-index for large repository worktrees

**Issue:** Sparse checkouts can still carry an index proportional to every path at HEAD, leaving status and index updates slow in very large repositories.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Git's sparse-index represents entire directories outside the sparse-checkout cone with sparse directory entries. For suitably shaped repositories, this changes some index operations from scaling with all paths at HEAD toward scaling with the populated paths.

Enable sparse checkout in cone mode and then opt into the sparse index using supported Git commands. Treat it as a working-tree optimization: it does not remove repository objects already present, and command support must be validated against the Git version and tooling used by developers and runners.

## Operational controls

- Define a cone that includes every path needed for builds, generators, tests, policy checks, and dependency discovery.
- Pin or establish a minimum Git version across the fleet.
- Test IDEs, linters, build tools, hooks, and scripts for assumptions that every path is materialized.
- Never use sparse checkout to omit required security or compliance checks.
- Record the sparse specification in reproducible runner setup rather than relying on mutable local state.
- Provide a documented path back to a full index and full working tree for diagnosis.

## Verification

1. Benchmark clone/setup, `status`, `add`, and representative builds before and after sparse-index adoption.
2. Compare artifacts and test counts with a full checkout at the same commit.
3. Modify paths at cone boundaries and confirm Git reports changes correctly.
4. Run repository-wide policy checks from a full checkout as the authoritative gate.
5. Disable sparse-index and sparse-checkout to verify recovery.

## Sources

- [Git: sparse-index](https://git-scm.com/docs/sparse-index)
- [Git: sparse-checkout](https://git-scm.com/docs/git-sparse-checkout)
