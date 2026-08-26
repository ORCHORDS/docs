# macOS runner toolchain image governance

**Issue**

Mutable Xcode, SDK, simulator, Homebrew, and command-line-tool state makes a persistent Mac fast but can make builds irreproducible across hosts.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Publish an inventory manifest with macOS build, Xcode build, SDKs, runtimes, package-manager state, and runner version.
- Route jobs by a tested capability label and select Xcode explicitly with supported tooling.
- Canary image changes with the full required-check suite before fleet promotion.
- Keep downloadable caches separate from the immutable toolchain baseline.

## Verification

1. Compare inventory and build outputs across every runner in a label pool.
2. Cold-build after deleting project caches.
3. Upgrade one canary and verify signing, simulator, compile, test, and archive jobs.

## Gotchas

- `xcode-select` is host-global and unsafe to mutate concurrently.
- Simulator runtimes consume substantial disk.
- Preinstallation saves time but does not validate the selected toolchain.

## Official sources

- [Apple xcode-select manual](https://keith.github.io/xcode-man-pages/xcode-select.1.html)
- [GitHub custom images for runners](https://docs.github.com/en/actions/how-tos/manage-runners/larger-runners/use-custom-images)
