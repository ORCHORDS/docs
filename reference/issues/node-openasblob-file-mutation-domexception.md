# Node openAsBlob file-mutation failure

**Issue:** Node fs.openAsBlob creates a file-backed Blob and detects file modification; later reads can fail with DOMException.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Treat source immutable for Blob lifetime, snapshot when writers coexist, close lifecycle explicitly and bound file size.

## Tests

Modify/truncate/replace after open, concurrent stream, deletion, permissions, large file.

## Gotchas

Blob creation success does not guarantee later reads after filesystem mutation.

## Official sources

- https://nodejs.org/api/fs.html#fsopenasblobpath-options
