# date-timezone-implicit-local

**Issue:** `new Date('2026-08-11')` parses as UTC midnight but `new Date('2026-08-11T00:00:00')` parses as local midnight, producing a one-day-off error
**Date:** 2026-08-11
**Status:** documented

## Symptom
A date stored as `2026-08-11` is displayed as `2026-08-10` for users west of UTC. Or a date comparison fails because one date was constructed from a date-only string (UTC) and another from a datetime string (local).

## Root cause
Per the ECMAScript spec: date-only strings (`YYYY-MM-DD`) are parsed as UTC; date-time strings without a timezone suffix (`YYYY-MM-DDTHH:mm:ss`) are parsed as local time. The inconsistency is a known spec quirk.

## Fix
Always include a timezone offset or use UTC methods explicitly:
```ts
// Ambiguous — avoid
new Date('2026-08-11')           // UTC midnight
new Date('2026-08-11T00:00:00')  // local midnight

// Explicit UTC
new Date('2026-08-11T00:00:00Z')

// Or use date-fns/parseISO which handles this consistently
import { parseISO } from 'date-fns';
parseISO('2026-08-11'); // UTC midnight, consistent
```

## Detection
```
grep -rn "new Date('" src/ --include="*.ts" | grep -v "Z'\|+00"
```

## Related
- `date-tostring-vs-toisostring.md`
