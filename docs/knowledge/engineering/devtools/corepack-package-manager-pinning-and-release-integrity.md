# Corepack package-manager pinning and release integrity

**Issue:** Different package-manager versions can interpret lockfiles or installation behavior differently across developer and CI environments.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use the project `packageManager` metadata and Corepack where supported to declare the intended package-manager release. Pin an exact reviewed version and commit the authoritative lockfile.

Corepack availability and distribution change across Node.js releases, so runner images must verify it explicitly rather than assuming every Node installation bundles an enabled shim. Package-manager pinning does not replace registry integrity, lockfile review, or dependency provenance checks.

## Controls

- Pin Node and package-manager versions.
- Verify downloaded package-manager releases through supported integrity mechanisms.
- Provision tools before restricted-network jobs.
- Fail on unexpected lockfile changes.
- Do not embed registry credentials in project metadata.
- Test the documented bootstrap path from a clean host.

## Verification

1. Bootstrap from a clean pinned Node environment.
2. Confirm the invoked package-manager version.
3. Run a frozen install and verify no lockfile changes.
4. Test offline or restricted-network behavior.
5. Change the declared version and confirm review-visible effects.

## Sources

- [Node.js: Corepack](https://nodejs.org/api/corepack.html)
- [Node.js: package.json packageManager field](https://nodejs.org/api/packages.html#packagemanager)
