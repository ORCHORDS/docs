# npm SBOM generation scope and reproducibility

**Issue:** An SBOM can omit workspace or installed dependency context, vary across tool versions, or be mistaken for proof that components are safe.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

`npm sbom` generates SPDX or CycloneDX inventories from the project dependency tree. Pin npm, format, SBOM type, workspace selection, omit settings, and whether generation uses the lockfile-only view.

## Controls and verification

- Generate after a frozen install when installed-state evidence is required.
- Include every intended workspace.
- Record source commit, lockfile digest, npm version, and command.
- Validate output against the selected schema.
- Keep vulnerability, license, signature, and provenance analysis separate.
- Rebuild twice from clean state and compare normalized component identities.

## Sources

- [npm: npm sbom](https://docs.npmjs.com/cli/commands/npm-sbom/)
- [CycloneDX specification](https://cyclonedx.org/specification/overview/)
- [SPDX specifications](https://spdx.dev/use/specifications/)
