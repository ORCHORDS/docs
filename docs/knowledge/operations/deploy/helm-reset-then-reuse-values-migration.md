# Helm reset-then-reuse values migration

**Issue**

Combining old release values with new chart defaults can preserve removed keys or silently miss newly required structure.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `--reset-then-reuse-values` only after rendering and schema validation.
- Diff effective values and manifests against explicit approved inputs.
- Keep rollback values with the release artifact.

## Verification

1. Upgrade across removed, renamed, and newly defaulted keys.
2. Compare reuse, reset, and reset-then-reuse modes.
3. Rollback and re-upgrade.

## Gotchas

- CLI precedence changes behavior.
- Old values can survive chart refactors.
- Schema validation does not prove runtime safety.

## Official source

- [Official documentation](https://helm.sh/docs/helm/helm_upgrade/)
