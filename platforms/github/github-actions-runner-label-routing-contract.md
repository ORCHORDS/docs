# Runner label routing is a compatibility contract

**Issue**

A job is dispatched only to a runner matching all requested labels and group constraints. Renaming or overloading labels can strand required checks or run them on incompatible machines.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define labels from capabilities with owners and tests, not host nicknames.
- Use runner groups for trust boundaries and labels for compatible execution characteristics.
- Publish a canary workflow for every supported label conjunction.
- Change routing in two phases: add/test new capacity, update workflows, then remove old labels.

## Verification

1. Dispatch every label contract and assert OS, architecture, toolchain, and privilege expectations.
2. Remove one capacity class and verify jobs remain queued rather than silently running on an incompatible fallback.
3. Audit repository access to each runner group.

## Gotchas

- Labels are not a security boundary without runner-group access control.
- All labels in `runs-on` must match.
- Generic `self-hosted` routing can be too broad.

## Official sources

- [GitHub using self-hosted runners in workflows](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/use-in-a-workflow)
