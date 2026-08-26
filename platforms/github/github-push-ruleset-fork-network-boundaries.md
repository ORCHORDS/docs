# GitHub Push-Ruleset Fork-Network Boundaries

**Issue:** A push restriction on a private or internal repository can unexpectedly affect every repository in its fork network, while bypass authority remains rooted upstream.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Map the complete fork network before activating push rules that restrict paths, path length, extensions, or file size.
- Define restrictions at the root repository with awareness that they apply across the network.
- Grant bypass only at the root and verify that fork administrators cannot create independent bypass actors.
- Use precise `fnmatch` patterns and document limits and exceptions for generated, vendored, binary, and migration content.
- Test representative contributor workflows before enforcing rules on active forks.

## Verification

- Push restricted and allowed fixtures to the root and multiple forks using normal and privileged accounts.
- Test path separators, nested paths, case variants, extensions, file-size boundaries, and multi-ref pushes.
- Confirm bypass events and rule changes are visible in the appropriate governance evidence.

## Gotchas

- Verify source maturity and product support before making a normative claim.
- Keep secrets, tokens, personal data, and restricted evidence out of examples and logs.
- Reassess after material changes to scope, dependencies, or enforcement.

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
