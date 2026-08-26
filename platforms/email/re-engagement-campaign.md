# re-engagement-campaign

**Issue:** Re-engaging inactive subscribers before sunset or list pruning
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Inactive subscribers hurt deliverability and skew engagement metrics; a re-engagement campaign recovers some before suppression.

## Pattern / Solution
Definition of inactive: no opens or clicks in 90-180 days.

Sequence:
1. **Email 1** (Day 0): "We miss you" — reminder of value, easy re-engagement CTA.
2. **Email 2** (Day 7): Last chance — "We'll stop emailing you unless you'd like to stay."
3. **No response:** Add to suppression list, remove from active segments.

Implementation:
```js
const inactive = await db.query(`
  SELECT * FROM subscribers
  WHERE last_engagement_at < NOW() - INTERVAL '90 days'
  AND status = 'active'
`);
await drip.enroll(inactive, 're-engagement-sequence');
```

## Gotchas
- Do not run re-engagement on transactional-only subscribers.
- Confirm-to-stay link should re-activate the subscriber with a single click (no form).
- Some inactive users will mark re-engagement as spam; send from a separate IP if possible.
- GDPR: inactivity alone doesn't justify deleting data; suppression is not deletion.

## Related
- email-sunset-policy, suppression-list-management, email-fatigue-prevention, drip-campaign-architecture
