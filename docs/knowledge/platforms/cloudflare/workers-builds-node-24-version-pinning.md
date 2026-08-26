# Workers Builds Node.js 24 reproducibility boundary

**Issue:** Workers Builds changed its default to Node.js 24.18.0 on 2026-07-30 while retaining Node.js 22.23.2. A build that inherits the platform default can change without a repository commit.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Declare the supported Node major in `.node-version`, `.nvmrc`, or `NODE_VERSION`; keep the package-manager version pinned separately.
- Test the next Node major before changing the pin and bind generated artifacts to the source SHA, lockfile, runtime, and build image evidence.
- Treat a platform-default change as a controlled toolchain migration, not routine rerun noise.

## Verification

1. Rebuild the same commit twice with a clean cache and compare checksums or explain nondeterministic fields.
2. Run lockfile, native-addon, and framework build checks on both old and candidate Node versions.
3. Prove the build log states the selected version.

## Gotchas

Pinning only `engines.node` may not select the Workers Builds runtime. A warm dependency cache can conceal native-addon or postinstall incompatibility.

## Official sources

- https://developers.cloudflare.com/changelog/product/workers/
- https://developers.cloudflare.com/workers/ci-cd/builds/configuration/
