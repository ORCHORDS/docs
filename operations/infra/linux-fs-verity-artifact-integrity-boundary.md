# Linux fs-verity artifact integrity boundary

**Issue:** Large read-only artifacts on writable filesystems can be modified after an initial checksum, while rehashing entire files before every partial read is expensive.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Enable fs-verity only on supported filesystems and immutable finalized artifacts. Authenticate the fs-verity digest through a separately trusted manifest or signature and verify policy before use. Keep update flow copy-then-enable rather than attempting in-place mutation.

## Verification

Enable verity on a disposable artifact, verify its digest against the trusted manifest, corrupt backing data in an isolated test, and confirm subsequent reads fail. Test kernel, filesystem, backup, and restore compatibility.

## Gotchas

fs-verity provides integrity, not authenticity, unless userspace or kernel policy authenticates the digest. It makes a file read-only and is not a replacement for dm-verity on a whole immutable filesystem.

## Official sources

- https://docs.kernel.org/filesystems/fsverity.html
