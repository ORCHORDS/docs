# Logpush subrequest-merging completeness

**Issue:** HTTP-request Logpush can merge qualifying subrequests into a parent record, but only up to 50 and within five minutes; others remain separate.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Version parser for nested and standalone records, deduplicate by stable identifiers, monitor overflow/late records, limit to supported zone dataset.

## Tests

49/50/51 subrequests, >5-minute completion, rollout absent, duplicates, schema evolution.

## Gotchas

Merged mode is not one-record completeness and is not available on every zone.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-04-21-logpush-subrequests-merging/
