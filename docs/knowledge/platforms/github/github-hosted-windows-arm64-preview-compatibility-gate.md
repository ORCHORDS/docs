# GitHub-hosted Windows arm64 preview compatibility gate

**Issue:** Windows arm64 hosted runner images in public preview require explicit compatibility checks for actions, installers, native binaries, and architecture-dependent build outputs.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin the explicit arm64 label; inventory action/runtime support; verify downloaded binary architecture and signature; keep a justified x64 comparison lane until parity is proven.

## Verification

Build/test native and managed code on both architectures; exercise installers, path/tool discovery, packaging, and artifact execution on arm64.

## Gotchas

Preview images are provided as-is and may change. Emulation can conceal native incompatibility and `-latest` does not express the intended architecture.

## Official sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
