# PostgreSQL WAL-summary retention budget

**Problem**

Incremental backup depends on WAL summaries whose retention must cover the chosen base backup and recovery workflow.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when operating PostgreSQL incremental backups.

## Controls

- Set `wal_summary_keep_time` from backup cadence and recovery objectives.
- Monitor summary availability and storage.
- Retain full-backup fallback.

## Implementation

- Bind incremental backups to a verified base manifest.
- Check required summary range before starting.
- Rehearse combine and restore.

## Tests

- Test within/beyond retention, timeline changes, failover, interrupted backup, and restore.

## Gotchas

- Summary retention is not WAL archive retention.
- Missing summaries block an incremental path.
- Backups need restore verification.

## Official sources

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-wal.html)
