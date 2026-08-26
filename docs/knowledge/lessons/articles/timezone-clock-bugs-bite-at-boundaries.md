# timezone-clock-bugs-bite-at-boundaries

**Issue:** A billing job double-charges 4% of customers the night daylight-saving time ends; a scheduled report fires an hour late for a week each spring; a session-expiry check trusts a client-supplied timestamp and lets a replayed request through. Date/time bugs are a distinct class of defect — a 2025 MSR empirical study catalogued them as their own taxonomy (timezone, DST, unit confusion, locale formats) — and they cluster at boundaries: DST transitions, midnight, month-ends, and timezone borders. This article captures where these bugs hide, why "store everything in UTC" is necessary but insufficient, and the rules and tests that prevent them.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Where the bugs hide

1. **DST transitions create nonexistent and duplicated local times.** In spring, 02:30 local doesn't exist once a year; in fall, 01:30 local happens twice. Any daily job scheduled by local wall-clock time can silently skip a run or run twice — the double-run is the one that double-charges. Recurring schedules must be anchored to UTC or to an offset-aware representation.
2. **Arithmetic on naive local times crosses zones invisibly.** Adding 24 hours to a naive local timestamp lands 23 or 25 real hours around a DST change, and "same time tomorrow" is not "now + 24h". A calendar event that should stay pinned to 9am local drifts by an hour after the first transition unless computed in the target zone.
3. **Future events stored as UTC go stale when zone rules change.** Governments change DST rules with little notice; a stored future UTC instant encodes today's rules, not the rules on the event day. The 2025-era guidance (W3C, and the accumulated "falsehoods programmers believe about time" literature) is to store future wall-clock events as local time plus an IANA zone identifier and derive the UTC instant lazily.
4. **Client clocks lie.** Trusting a browser or device timestamp for ordering, expiry, or rate limiting lets any client fabricate "the past". Client time is display data, never authority: server time (or better, a monotonic authority) decides, and client skew is only measured, never obeyed.
5. **Formatting and parsing drift across locales.** `03/04/2026` is March 4 or April 3 depending on locale; `YYYY` vs `yyyy` in format strings produce different results near year boundaries; and week-numbering schemes differ by country. Every parse of a human-format string without an explicit locale and format is a latent data-corruption bug.

## Root causes

1. **Programmers model time as a number instead of a pair.** An instant (a moment on the physical timeline) and a wall-clock reading (what a clock in a zone shows) are different types that both look like "a datetime". Most bugs in the MSR-style taxonomies collapse to using one where the other is required, and the primitive date types of many languages don't force the distinction.
2. **"UTC everywhere" is applied as a slogan, not a boundary rule.** UTC is the right storage and interchange format for instants, but it is the wrong format for future local schedules and the wrong format for human display. Teams that convert too early (or too late) across the storage/logic/display boundary corrupt the one representation the user actually cares about.
3. **The timezone database is invisible infrastructure.** IANA tzdata ships inside runtimes and OSes, so deployments end up with mixed versions — one service on the 2024 rules, another on 2026 rules — producing disagreement about when an event occurs. Tzdata must be pinned and updated like any other dependency.
4. **Tests never run at the interesting times.** A suite that executes at 14:07 UTC on a normal Tuesday proves nothing about behavior at 02:00 during a transition, at month-end, or on February 29. Time-dependent code tested only with "now" is untested for exactly the inputs that break it.
5. **Timezone handling is smeared through app code instead of centralized.** When every module does its own conversion, rounding, and formatting, the same instant gets interpreted differently in different subsystems — the audit log disagrees with the invoice, and reconciliation fails. Conversion belongs at boundaries, in one place, with one policy.

## Rules that prevent them

1. **Store instants as UTC (or epoch) with timezone-aware types; store future local events as wall-clock + IANA zone.** Never store a naive datetime in a shared system — make the type system or schema forbid it. This single rule eliminates the majority of the taxonomy.
2. **Do all arithmetic on instants; do all display in the user's zone, at render time.** Convert at the edges: parse-in converts immediately to an instant, render-out converts immediately to a zone. No business logic operates on local wall-clock values.
3. **Inject the clock.** Every component that reads "now" takes a clock dependency, so tests can pin it, replay it, and jump it. The same applies to sleep/timers in tests — control them, never wait for them.
4. **Pin and update tzdata deliberately.** Track the IANA release in your runtime images, update it on a schedule, and note it in release notes — a DST-rule change is an externally-forced behavior change to your scheduling system, not a no-op patch.
5. **Anchor recurring jobs to UTC instants or durations, never local wall-clock.** If a job must run "at 9am local for each customer", compute the next run per zone at scheduling time and store the resulting instant, re-deriving after each run so rule changes are absorbed.

## Testing strategies

1. **Run the suite at hostile fake times.** Include pinned "now" values at the DST spring-forward and fall-back transitions (in a zone that has them), at 23:59:59 UTC, on month-end, on Feb 29, and on Dec 31. These are the coordinates from the empirical bug taxonomies — test them explicitly.
2. **Test both hemispheres and zone oddities.** Zones with half-hour offsets, zones that abandoned DST mid-decade, and northern/southern DST opposition expose assumptions baked in by testing only against one home timezone.
3. **Round-trip every serialization.** For each stored/transported timestamp format, assert write-then-read produces the identical instant and zone metadata, with a case where the local time is duplicated by a DST fallback.
4. **Assert on interval boundaries, not midpoints.** Tests for expiry, retention, and billing windows should exercise the exact boundary (0s before, 0s after, and the duplicated hour) rather than comfortable values far from edges — off-by-one-boundary is the dominant defect shape.
5. **Verify mixed-version behavior.** Deliberately run services with mismatched tzdata versions in a test environment once to confirm graceful behavior (or a loud error) rather than silent disagreement, before reality does it for you during a partial rollout.
