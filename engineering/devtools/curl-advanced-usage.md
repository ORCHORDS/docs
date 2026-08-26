# curl-advanced-usage

**Issue:** Basic curl usage but not leveraging config files, retry, or verbose debugging
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Repetitive curl flags typed each time; no retry logic; auth headers visible in shell history.

## Pattern / Solution
~/.curlrc for default options. -u user:pass or --netrc-file. --retry 3 --retry-delay 2. Debug: -v for headers, --trace-ascii - for full dump. --write-out for timing breakdown.

## Gotchas
- Avoid putting credentials in command line — use --netrc or env var interpolation
- -L follows redirects; essential for HTTPS URLs that redirect from HTTP

## Related
- httpie-patterns, jq-json-processing
