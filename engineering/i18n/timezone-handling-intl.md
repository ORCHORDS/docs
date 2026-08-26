# timezone-handling-intl

**Issue:** Displaying times in the user's local timezone using Intl APIs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
UTC timestamps must be displayed in the viewer's timezone. Hard-coding the server timezone causes wrong times for remote users.

## Pattern / Solution
```js
const utcDate = new Date('2026-08-11T14:00:00Z');

const userTZ = Intl.DateTimeFormat().resolvedOptions().timeZone;
// -> 'America/New_York'

new Intl.DateTimeFormat('en-US', {
  timeZone: userTZ,
  dateStyle: 'medium',
  timeStyle: 'short',
}).format(utcDate);
// -> 'Aug 11, 2026, 10:00 AM'

// List supported timezones
Intl.supportedValuesOf('timeZone');

// Show offset
new Intl.DateTimeFormat('en-US', {
  timeZone: 'Asia/Tokyo',
  timeZoneName: 'shortOffset',
}).format(utcDate);
// -> '8/11/2026, GMT+9'
```

## Gotchas
- `timeZone` option requires IANA tz database names, not abbreviations like EST
- Server-rendered pages hardcode server timezone unless SSR is timezone-aware
- DST transitions mean some local times occur twice; use Temporal for disambiguation

## Related
- `date-formatting-intl.md`
- `timezone-iana-temporal-2026.md`
