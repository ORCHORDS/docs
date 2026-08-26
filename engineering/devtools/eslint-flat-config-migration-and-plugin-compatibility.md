# ESLint flat-config migration and plugin compatibility

**Issue:** Migrating lint configuration can silently change file selection, ignores, plugin resolution, or rule coverage.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Migrate to ESLint flat configuration with an explicit file and ignore model. Audit every plugin, parser, shareable configuration, and CLI integration for the pinned ESLint release.

## Controls and verification

- Capture the pre-migration linted-file list and violations.
- Use configuration inspection on representative files.
- Replace implicit ignore assumptions explicitly.
- Pin compatible plugin/parser versions.
- Keep generated, vendored, and security-sensitive paths deliberate.
- Require equal or stronger rule coverage before removing legacy config.

## Sources

- [ESLint: Configuration migration guide](https://eslint.org/docs/latest/use/configure/migration-guide)
- [ESLint: Configuration files](https://eslint.org/docs/latest/use/configure/configuration-files)
