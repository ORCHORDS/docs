# r2-lifecycle-rules

**Issue:** Automatically expiring or transitioning R2 objects using lifecycle rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
R2 lifecycle rules automatically delete objects after a specified number of days, which is essential for managing temporary uploads, log archives, and cost control.

## Pattern / Solution

**Set lifecycle rules via Wrangler:**
```bash
wrangler r2 bucket lifecycle set my-bucket --file lifecycle.json
```

```json
// lifecycle.json
{
  "rules": [
    {
      "id": "delete-temp-uploads",
      "enabled": true,
      "prefix": "temp/",
      "expiration": {
        "days": 1
      }
    },
    {
      "id": "delete-old-logs",
      "enabled": true,
      "prefix": "logs/",
      "expiration": {
        "days": 90
      }
    },
    {
      "id": "delete-expired-presigned",
      "enabled": true,
      "prefix": "uploads/",
      "expiration": {
        "days": 7
      }
    }
  ]
}
```

**Set via REST API:**
```bash
curl -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/r2/buckets/my-bucket/lifecycle" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d @lifecycle.json
```

**Get current rules:**
```bash
wrangler r2 bucket lifecycle get my-bucket
# or
curl "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/r2/buckets/my-bucket/lifecycle" \
  -H "Authorization: Bearer $CF_TOKEN"
```

**Delete rules:**
```bash
wrangler r2 bucket lifecycle delete my-bucket
```

**Pattern: auto-clean temporary uploads from Worker:**
```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const key = `temp/${crypto.randomUUID()}`;

    // Upload — lifecycle rule handles cleanup after 1 day
    await env.R2.put(key, request.body, {
      customMetadata: { uploadedAt: new Date().toISOString() },
    });

    return Response.json({ key, expiresIn: '24h' });
  },
};
```

## Gotchas
- Lifecycle rules are evaluated **once per day** — deletion may happen up to 24 hours after the expiration day.
- `prefix` is matched against the object key from the start — `logs/` matches `logs/2026/01/file.log` but not `archive/logs/file.log`.
- There is no "transition to cold storage" tier in R2 (unlike S3 Glacier) — rules only support expiration.
- Rules with overlapping prefixes: the most specific (longest) prefix takes precedence.
- Deleted objects are **not** recoverable unless you have event notifications pointing to a backup.
- Maximum 1000 lifecycle rules per bucket.
- Rules do not apply retroactively to objects uploaded before the rule was created if they are already past the expiration age — they apply at the next daily evaluation.

## Related
- `r2-best-practices.md`
- `r2-event-notifications.md`
- `r2-large-file-patterns.md`
