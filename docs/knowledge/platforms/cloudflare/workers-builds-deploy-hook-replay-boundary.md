# Workers Builds deploy-hook replay boundary

**Issue:** A Deploy Hook is a branch-bound bearer URL that triggers build and deploy by POST. Cloudflare deduplicates triggers queued before a build starts and rate-limits hooks, but that is not business-event idempotency.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Store the hook only as a secret; rotate after exposure; authenticate the upstream event separately; map allowed source to branch; serialize release-critical builds and verify deployed SHA.

## Verification

Replay, burst, reorder, and forge trigger requests; hit per-Worker/account limits; rotate the hook; prove duplicate source events do not deploy unintended content.

## Gotchas

Built-in dedup applies only before the first build starts. Possession of the URL is authority, and a successful POST does not prove the desired commit reached production.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-04-01-deploy-hooks/
