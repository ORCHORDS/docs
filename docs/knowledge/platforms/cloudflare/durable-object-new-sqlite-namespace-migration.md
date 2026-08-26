# Durable Object new SQLite namespace migration

**Issue:** Accounts without legacy KV-backed namespaces must create new Durable Object classes with new_sqlite_classes.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls and implementation

Use append-only migration tags, stage bindings, test PITR and SQL/KV APIs, retain rollback/mapping evidence.

## Tests

Fresh account deploy, existing account, wrong new_classes, rollback, restore.

## Gotchas

Backend choice is namespace creation state; changing config does not convert existing namespaces.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-07-09-restrict-new-kv-backed-namespaces/
