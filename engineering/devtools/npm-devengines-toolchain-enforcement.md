# npm devEngines toolchain enforcement

**Issue:** Contributors and CI can run incompatible Node, npm, operating-system, CPU, or libc combinations and discover the mismatch only after an opaque build failure.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Declare reviewed runtime and package-manager requirements in package.json `devEngines`, including versions and `onFail: error` for unsupported combinations. Keep runtime deployment constraints separately in `engines`; pin CI setup independently because metadata is not a download mechanism.

## Verification

Run `npm ci` and representative scripts on the supported matrix and one deliberately unsupported toolchain. Confirm failure occurs before installation and document the upgrade path.

## Gotchas

`devEngines` and `engines` have different shapes and purposes. Alternate package managers may not enforce npm behavior identically; do not claim platform support that CI does not exercise.

## Official sources

- https://docs.npmjs.com/cli/configuring-npm/package-json/#devengines
