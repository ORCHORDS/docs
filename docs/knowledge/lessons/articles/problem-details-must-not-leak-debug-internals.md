# Problem Details Must Not Leak Debug Internals

**Issue:** An API reuses internal exception messages as public problem details, exposing implementation information and creating a brittle client dependency on debugging text.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

RFC 9457 explicitly separates interface-level problem information from implementation debugging. The `detail` member is human-readable guidance for this occurrence; consumers should not parse it, and producers should not use it as a transport for stack traces, query text, secrets, internal paths, or other implementation detail.

## Engineering rule

- Map internal failures to a controlled public problem type.
- Keep `detail` focused on what the caller can understand or correct.
- Put correlation identifiers in an intentionally designed field if support needs them.
- Keep stack traces and diagnostic context in protected server-side telemetry.
- Review new problem types for information-disclosure risk before release.

## Verification

- Trigger representative 4xx and 5xx paths and scan responses for stack traces, internal file paths, queries, credentials, and private hostnames.
- Confirm localized or rewritten `detail` strings do not alter client behavior.
- Confirm server logs retain the diagnostic evidence omitted from the public response.

## Official source

- RFC 9457, Problem Details for HTTP APIs: https://www.rfc-editor.org/rfc/rfc9457.html
