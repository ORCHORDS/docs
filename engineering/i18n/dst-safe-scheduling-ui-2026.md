# dst-safe-scheduling-ui-2026

**Issue:** Calendar and scheduling UIs break in ways that unit tests never catch whenever a daylight saving time (DST) transition occurs. Recurring events silently shift by an hour, events vanish or duplicate during the spring-forward gap, and fall-back produces ambiguous local times that resolve to the wrong instant. Because most teams develop in a single timezone and test on dates far from any transition, these bugs ship to production and surface twice a year as support spikes. A DST-safe scheduling feature requires deliberate storage modeling (absolute instants versus wall-clock recurrences), explicit handling of nonexistent and ambiguous times, and UI affordances that tell users what will happen to their event after the next transition.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Data model decisions

1. **Store one-off events as absolute instants.** A single meeting on a fixed date is an exact moment in time: persist it as a UTC timestamp (or epoch milliseconds) plus the originating IANA zone for display. Never store a fixed numeric offset like -05:00, because the offset is only valid for part of the year and will be wrong after the next transition.

2. **Store recurring events as local wall-clock time plus an IANA zone ID.** A weekly 9:00 AM standup means 9:00 AM local to the organizer on every occurrence, before and after DST. Persisting wall time (hour, minute, weekday) with a zone like America/New_York lets the recurrence engine recompute the correct UTC instant per occurrence using zone rules. Persisting the first occurrence's UTC time instead freezes the offset and drifts an hour after each transition.

3. **Normalize and keep zone data current.** DST rules change by legislation (countries have abolished, reinstated, and reshuffled transitions as recently as the 2020s). Ship the IANA tzdb (via the platform, or date-fns-tz/Luxon/Temporal polyfill data) and track its version, because a stale tzdb silently produces wrong instants for future dates.

4. **Prefer interval triggers over cron expressions for job schedulers.** Cron-style schedules are defined in local server time and either shift or skip across transitions; the PingOne scheduling documentation explicitly recommends simple interval triggers to keep job start times stable across DST. If cron must be used, anchor it to UTC and document the choice.

## Edge cases to handle explicitly

1. **Nonexistent times during spring forward.** When clocks jump from 2:00 to 3:00 AM, the local time 2:30 AM does not exist. A datetime picker must either block that window, warn, or apply a documented resolution strategy (push forward to 3:30 AM is the common choice). Silently accepting it produces an instant the library resolves arbitrarily.

2. **Ambiguous times during fall back.** When clocks fall back, 1:30 AM occurs twice. If a user picks it, ask which occurrence (early or late) or disambiguate with a hint like "occurs twice — times after 2:00 AM are one hour earlier"). JavaScript's Date resolves ambiguity by picking the earlier offset; that may not be what the user meant.

3. **Events that straddle a transition.** An event scheduled from 1:45 to 2:15 AM on a transition night has a duration that differs from its wall-clock span. Compute durations from instants, never from wall-clock subtraction, and recompute long-running events' end times after resolving their start instants.

4. **Reminder offsets.** A "remind me 15 minutes before" flag must be anchored to the resolved instant of each occurrence, not to a fixed UTC time captured once, or reminders drift by exactly the DST delta.

## UI communication patterns

1. **Show the timezone on every scheduled item.** Render times with an explicit zone indicator (9:00 AM America/New_York, or 9:00 AM ET) so cross-zone participants can convert mentally. For multi-zone audiences, show the viewer's local equivalent next to the organizer's time.

2. **Warn when a future occurrence lands on a transition.** When a user creates a recurring event whose next occurrence crosses a DST boundary, display an inline notice ("after November 2, this will be 8:00 AM EST") instead of letting them discover the shift later. Sentry's post-mortem of calendar DST bugs (the FullCalendar case study) shows users interpret the silent shift as data corruption.

3. **Make participant-local rendering the default.** Each viewer should see times converted to their own zone; the anti-pattern is rendering the organizer's zone for everyone and forcing mental math, which multiplies the harm of any DST drift.

4. **Business hours are wall-clock, not instants.** Store opening hours as local wall time in the venue's zone. The classic pitfall (documented across booking-system discussions) is persisting business hours as UTC times, which makes a shop appear to open an hour off for half the year.

## Testing strategy

1. **Test on transition dates.** Include fixture dates for both the spring-forward and fall-back nights of several zones (US, EU, which transition on different dates, and Southern Hemisphere zones like Australia/Sydney, which transition in opposite months).

2. **Test zones without DST as controls.** Asia/Tokyo and Africa/Nairobi never transition; they isolate bugs caused by recurrence logic from bugs caused by offset math.

3. **Adopt Temporal for new code.** The TC39 Temporal proposal (shipping in browsers through 2025-2026) models ZonedDateTime natively, makes offset disambiguation explicit via an option, and removes most footguns of the legacy Date object. Plan migration rather than patching Date-based DST math indefinitely.

4. **Add a DST canary job.** Run a scheduled CI check twice a year on the actual transition nights (or simulate them by freezing the clock) that verifies recurring events resolve to expected instants, catching tzdb regressions and logic drift before users do.
