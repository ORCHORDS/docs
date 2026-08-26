# PostgreSQL vacuum failsafe and transaction-ID wraparound risk

**Issue:** Aggressive cost delay or blocked vacuum can let transaction ages approach wraparound, forcing emergency behavior and threatening availability.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

PostgreSQL vacuum failsafe can bypass normal cost delays and some nonessential work when table age approaches configured failsafe thresholds. It is a last-resort safety behavior, not normal capacity planning.

## Controls and verification

- Alert on database and relation transaction/multixact age well before failsafe.
- Find long transactions, old slots, and locks that block cleanup.
- Size autovacuum workers and I/O from churn.
- Never disable or repeatedly cancel anti-wraparound vacuum casually.
- Track dead tuples, vacuum duration, freeze progress, and WAL/storage effects.
- Load-test high churn and verify routine vacuum keeps ages comfortably below failsafe.

## Sources

- [PostgreSQL 18: Routine vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html)
- [PostgreSQL 18: VACUUM configuration](https://www.postgresql.org/docs/current/runtime-config-vacuum.html)
