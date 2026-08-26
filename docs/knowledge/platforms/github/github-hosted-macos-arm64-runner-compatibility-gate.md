# GitHub-hosted macOS arm64 compatibility gate

**Issue:** GitHub-hosted arm64 macOS runners differ from Intel runners: community actions may not support arm64, nested virtualization is unavailable, and arm64 runners have no static UDID. macOS larger runners also lack static IP and Azure private networking.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin an explicit macOS image and architecture; inventory every action and binary for arm64 support.
- Keep signing in a protected environment and choose Intel only when its documented static UDID is genuinely required.
- Make architecture-specific exclusions visible and temporary rather than silently skipping checks.

## Verification

1. Compile and test native dependencies on both supported architectures.
2. Fail early on an x64-only action instead of downloading an unverified binary.
3. Verify signing, entitlements, simulator tests, and artifact checksums on the chosen lane.

## Gotchas

`macos-latest` is a moving label. Rosetta can hide portability defects, and arm64 nested virtualization cannot be enabled by workflow configuration.

## Official sources

- https://docs.github.com/en/actions/reference/runners/github-hosted-runners
