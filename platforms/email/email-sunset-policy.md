# email-sunset-policy

**Issue:** Implementing a sunset policy to automatically suppress chronically unengaged subscribers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Continuing to email unresponsive subscribers damages sender reputation; sunset policy removes them systematically.

## Pattern / Solution
Policy definition:
- **90-day inactive:** Run re-engagement campaign.
- **No response to re-engagement:** Add to sunset suppression list.
- **180-day inactive (without re-engagement):** Auto-sunset.

Implementation:
```sql
-- Identify sunset candidates
SELECT user_id FROM subscribers
WHERE last_engagement_at < NOW() - INTERVAL '180 days'
  AND status = 'active'
  AND re_engagement_sent_at < NOW() - INTERVAL '30 days'
  AND re_engagement_responded = false;
```

Sunset action: update status to `sunsetted`, log reason, do not delete.

Reactivation: if sunsetted user logs in or makes a purchase, reset engagement and reactivate.

## Gotchas
- Sunset is suppression, not deletion; GDPR deletion requests are separate.
- Transactional email should still be sent to sunsetted users (receipts, password reset).
- Run sunset monthly, not daily; large sudden list drops concern ISPs.
- Document sunset policy in privacy policy if required by jurisdiction.

## Related
- re-engagement-campaign, suppression-list-management, email-fatigue-prevention, email-list-hygiene
