# timestamp-timezone-handling

**Issue:** Timezone bugs are the most common class of silent data corruption in application databases: reports shift by a day, a daily digest sends twice during a DST changeover, and records written "2026-03-08 02:30" simply never existed. The root cause is almost always using `timestamp` (without timezone) where an instant was meant, storing local times where a wall-clock was meant, or letting session-level timezone settings reinterpret values during read/write. Postgres gives precise tools (`timestamptz`, `AT TIME ZONE`, `datestyle`) but they are frequently misapplied.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## timestamptz semantics that surprise people

1. **timestamptz stores no timezone.** Despite the name, it stores a single instant (internally UTC-normalized); the timezone you see on read is the session's `TimeZone` setting rendering that instant. The PostgreSQL wiki's "Don't Do This" page says it plainly: don't use `timestamp` for timestamps.
2. **Plain `timestamp` is a wall clock.** `timestamp without time zone` means "local civil time, no location" — correct only for events defined by their local time (a 9am meeting), never for "when did this actually happen".
3. **Literal interpretation depends on session timezone.** Inserting the string `'2026-08-15 10:00'` into a `timestamptz` column converts it from the session timezone to UTC; a pooler or cron job with a different `TimeZone` than the app writes different instants from the same string. Always send timestamptz values with an explicit offset (`+00`) or pass native datetime objects.
4. **Set the server and pool default to UTC.** `ALTER DATABASE app SET timezone = 'UTC'` and `PGTZ=UTC` in connection strings removes the ambiguity for every session, including ad-hoc psql. Convert to local time only in the presentation layer.

## DST edge cases that corrupt data

1. **Spring-forward gaps and fall-back repeats.** Local 02:30 on a spring-forward night exists zero times; local 01:30 on fall-back night exists twice. `timestamptz` handles both deterministically (gap times roll forward, repeated times pick the offset in force), while plain `timestamp` silently accepts the ambiguous or nonexistent value.
2. **Arithmetic across DST is not duration arithmetic.** `timestamp + interval '24 hours'` yields the same clock time tomorrow on a timestamptz (because it adds a real duration), while adding `interval '1 day'` can jump 23 or 25 hours — Postgres `day` arithmetic follows calendar days for plain timestamps and can differ across a transition. Test every recurrence calculation against both DST boundaries in your users' zones.
3. **"Same day" grouping needs a timezone.** `date_trunc('day', created_at)` on a timestamptz groups by UTC midnight; for a user-facing daily report use `date_trunc('day', created_at AT TIME ZONE 'America/New_York')`. Getting this wrong makes daily counts off by hours at the edges.
4. **Timezone rules change retroactively.** Governments move DST dates; the IANA database ships updates. Future instants stored as fixed UTC can shift their local meaning when rules change — a reminder to compute local renderings at display time, not store them.

## Future scheduled events: the one valid plain-timestamp use

1. **Store local time plus zone name.** A recurring 9am America/Chicago meeting must remain 9am local even after DST shifts; store `starts_at timestamp` (or `time`), a `tz text` column holding the IANA name (never an abbreviation like `CST`), and compute the next occurrence in the application or a function.
2. **Cache the next UTC occurrence.** Denormalize a `next_run_at timestamptz` column computed from local + tz, refresh it after each run, and index it for the scheduler query — storing both representations is the pragmatic pattern recommended in current discussions.
3. **Never store offsets for recurring events.** `UTC-05` stops being correct when Chicago switches to `UTC-06`; IANA names carry the full rule history and future rules.
4. **Validate tz names on write.** Check against `pg_timezone_names` or your platform's zone database so `'America/Chicgo'` fails loudly at insert instead of silently at run time.

## Cross-language and cross-database pitfalls

1. **JavaScript Date is always an instant.** A JS `Date` has no timezone yet `toISOString()` emits UTC with a `Z`; passing its local string parts into a `timestamp` column mixes semantics. Libraries like date-fns or Luxon with explicit zones prevent this.
2. **MySQL DATETIME vs TIMESTAMP differ fundamentally.** MySQL `TIMESTAMP` stores UTC and converts per-session like Postgres `timestamptz`, while `DATETIME` is a wall clock like Postgres `timestamp`; teams migrating between the two routinely misread one for the other.
3. **ORM defaults can betray you.** Some ORMs generate `timestamp` columns by default or serialize datetimes as local strings; audit generated DDL once and pin the mapping (e.g. Drizzle/Prisma `timestamptz`).
4. **Beware `now()` vs `clock_timestamp()` in tests.** `now()` is transaction-start time and fixed per transaction (good for consistent auditing), `clock_timestamp()` advances; tests asserting on sub-second ordering need the distinction.
5. **Keep one convention project-wide.** UTC `timestamptz` everywhere for instants, explicit IANA zones for schedules, conversion only at the edges — a rule enforced in code review is worth more than any single type choice.
