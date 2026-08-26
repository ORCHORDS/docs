# Node.js diagnostic-report privacy and trigger policy

**Issue:** Diagnostic reports are valuable during hangs and fatal errors, but they can persist environment variables, network details, paths, stacks, and runtime state as an unmanaged sensitive artifact.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin the Node.js release used in production and choose report triggers explicitly: fatal error, uncaught exception, operator signal, or a guarded `process.report.writeReport()` call. Write into a dedicated, quota-bound directory with restrictive permissions and an external retention policy. Enable `--report-exclude-env` when environment values are not required and `--report-exclude-network` when interface and endpoint data are unnecessary.

Treat a report as sensitive even with exclusions because stacks, command-line arguments, working paths, native handles, and application-provided error context can still disclose data. Do not write reports to shared stdout by default, and authorize signal-triggered collection separately from normal health checks. Signal triggering is not portable to Windows.

## Verification

Generate each enabled trigger in a disposable process, confirm the expected directory, ownership, name uniqueness, size bound, uploader encryption, and deletion. Scan a fixture report for seeded secrets and personal data. Exercise full disk, unwritable directory, concurrent reports, worker threads, and Windows behavior where supported.

## Gotchas

- Report schema versions can change across Node releases.
- Excluding environment and network sections is not complete redaction.
- Fatal-error paths may run when disk and memory are already constrained.

## Official source

- [Node.js diagnostic report](https://nodejs.org/api/report.html)
