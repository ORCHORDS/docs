# Durable Object deleteAll alarm compatibility date

**Issue:** For compatibility dates on or after 2026-02-24, storage deleteAll also deletes the Durable Object alarm; older behavior required separate deletion.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Pin compatibility date, make reset intent explicit, reschedule only after durable state is ready, document mixed-version rollout.

## Tests

Old/new dates, pending alarm, reset then crash, reschedule, rollback, concurrent alarm delivery.

## Gotchas

A compatibility-date bump can silently change reset semantics.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-02-24-deleteall-deletes-alarms/
