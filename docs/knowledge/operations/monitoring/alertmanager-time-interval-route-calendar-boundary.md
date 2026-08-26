# Alertmanager time-interval route calendar boundary

**Issue:** Business-hours and maintenance routing can page at the wrong local time or suppress the wrong sibling route when calendar, timezone, inheritance, and `continue` semantics are implicit.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define named `time_intervals` and reference them from child routes with `active_time_intervals` or `mute_time_intervals`; the root route cannot carry either.
- Set the timezone location explicitly and ensure the runtime contains the intended timezone database. Treat UTC as the fallback, not an assumed local zone.
- Review route traversal with the calendar rule: a muted or inactive matching route still participates in matching and can stop later siblings when `continue` is false.
- Keep paging fallback routes outside fragile holiday logic, and make ownership of exceptional dates explicit.
- Reload only validated configuration and record the effective config revision on every peer.

## Verification

Test interval edges, overnight spans, weekdays, month boundaries, leap day, daylight-saving transitions, holidays, absent timezone data, overlapping child routes, and both values of `continue`. Use fixed test timestamps and assert the exact receiver set.

## Gotchas

- Calendar intervals control notifications, not whether alerts continue firing or grouping.
- A timezone-database update can change future civil-time behavior without a YAML diff.
- Muting a route does not automatically route the alert to a later sibling.

## Official source

- [Alertmanager configuration: routes and time intervals](https://prometheus.io/docs/alerting/latest/configuration/#time_interval)
