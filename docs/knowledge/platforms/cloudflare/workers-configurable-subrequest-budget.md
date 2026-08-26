# Workers configurable subrequest budget

**Issue:** Paid Workers default to 10,000 subrequests and can configure higher or lower limits; free-plan external/internal limits differ.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Set the lowest measured limit, budget fan-out per code path, cap retries/pagination, alert near exhaustion.

## Tests

Worst-case graph, retry storm, websocket/workflow longevity, plan mismatch and lower-limit fail.

## Gotchas

A higher platform ceiling is not permission for unbounded fan-out and can amplify cost.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-02-11-subrequests-limit/
