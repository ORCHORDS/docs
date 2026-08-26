# npm audit signatures and registry key verification

**Issue:** Lockfile integrity detects changed package bytes but does not by itself establish that a registry-published version carries a valid registry signature or provenance attestation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Run `npm audit signatures` in a clean, lockfile-driven CI job using the intended registry. Pin the npm major version through the toolchain, preserve ordinary vulnerability auditing, and fail release gates on invalid signatures. For private registries, confirm signature and key endpoints implement npm's documented protocol before enforcing the gate.

## Verification

Exercise the gate on the committed lockfile, capture package and failure class without exposing auth headers, and confirm a deliberately unsupported registry is reported distinctly from an invalid signature. Keep `npm ci`, tests, and vulnerability checks enabled.

## Gotchas

Signature availability varies by registry and package history. A successful signature check does not assess package behavior, maintainer trust, vulnerabilities, or build reproducibility.

## Official sources

- https://docs.npmjs.com/cli/v11/commands/npm-audit/
- https://docs.npmjs.com/generating-provenance-statements
