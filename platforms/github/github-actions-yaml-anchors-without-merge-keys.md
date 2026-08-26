# GitHub Actions YAML Anchors Without Merge Keys

**Issue:** YAML anchors can reduce repetition in Actions workflows, but assuming general YAML merge-key behavior can create invalid or misleading configurations.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Use anchors and aliases only in syntax GitHub Actions documents as supported.
- Keep security-sensitive permissions, environments, and runner labels explicit at job boundaries.
- Validate workflow parsing after refactors and review fully expanded semantics.
- Prefer reusable workflows for governed behavior crossing repository boundaries.

## Verification

- Introduce supported aliases and confirm Actions accepts the workflow.
- Negative-test merge-key syntax if unsupported by the current platform.
- Compare effective permissions and matrices before and after refactoring.

## Gotchas

- YAML reuse is textual structure, not a policy inheritance system.
- Aliases can hide review-significant changes.

## Official sources

- https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations
