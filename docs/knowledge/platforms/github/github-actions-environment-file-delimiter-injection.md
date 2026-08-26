# GitHub Actions environment-file delimiter injection

**Issue:** Multiline writes to GITHUB_ENV/GITHUB_OUTPUT can be truncated or injected when untrusted content contains the chosen delimiter.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Use random per-write delimiters or files/artifacts for arbitrary data; never eval; validate size and encoding.

## Tests

Delimiter collision, CRLF, binary, percent/newline, hostile tool output.

## Gotchas

Environment files are command channels, not transparent blob storage.

## Official sources

- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands
