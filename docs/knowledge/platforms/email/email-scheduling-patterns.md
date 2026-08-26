# email-scheduling-patterns

**Issue:** Scheduling emails for optimal delivery timing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Time-based email scheduling (send at user's local 9am, send after 3-day trial ends) improves engagement and relevance.

## Pattern / Solution
1. **Fixed time:** Store `send_at` in UTC, schedule job:
```js
await emailQueue.add('send', data, { delay: sendAt.getTime() - Date.now() });
```
2. **Relative time:** Compute `send_at` from trigger event:
```js
const send_at = addDays(user.trialStartedAt, 3);
```
3. **Local time optimization:** Convert user's local 9am to UTC using timezone:
```js
import { fromZonedTime } from 'date-fns-tz';
const send_at = fromZonedTime('2026-08-12 09:00', user.timezone);
```
4. **Send-time optimization (ML):** ESPs like Mailchimp, Klaviyo offer this; or build with historical open-time data.

## Gotchas
- Store all timestamps in UTC; convert to user timezone only for display.
- Respect user timezone preference; inferred timezone from signup IP is unreliable.
- Daylight saving time transitions: use IANA timezone names (e.g., `America/New_York`) not offsets.
- Scheduled jobs that miss their time by >1 hour should be discarded, not sent late.

## Related
- drip-campaign-architecture, email-queue-architecture, triggered-email-patterns, email-batch-sending
