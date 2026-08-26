# R2 Lifecycle Rules for Cold Archival and Glacier Strategy

- Date: 2026-08-22
- Author: example.com
- Status: production

## Long-Term Object Retention on Cloudflare R2

R2's zero-egress pricing makes it attractive for archival, but without lifecycle rules hot-tier objects accumulate indefinitely and storage costs grow linearly with retention. As of 2026, R2 supports object lifecycle rules—expiration and transitioning objects between storage classes (Standard and Infrequent Access)—mirroring S3's lifecycle model. Infrequent Access (IA) class reduces per-GB storage cost at the expense of a per-operation retrieval fee, making it economically correct for objects accessed fewer than ~once per month.

Unlike AWS S3 Glacier, R2 does not have a deep-archive tier with restore latency. All retrieval from R2 IA is immediate, which simplifies restore patterns: no `RestoreObject` API call, no 12-hour wait, no expedited-restore surcharge. The tradeoff is that per-GB IA pricing is a fraction of Standard but retrieval costs are higher, so the break-even point is at low access frequency rather than zero access.

A scheduled Worker auditing lifecycle compliance closes the gap between what the lifecycle rule specifies and what is actually in the bucket. It is possible for objects to bypass lifecycle rules if they were uploaded before the rule was applied or if there are object-lock configurations in conflict. The audit Worker lists all objects older than the transition threshold and flags non-IA objects for manual review or forced transition.

## Context

- R2 bucket created with `wrangler r2 bucket create` or Terraform
- Lifecycle rules configured via `wrangler.toml` or Cloudflare API
- Workers Paid plan for scheduled Workers (cron)
- Cost targets: R2 Standard $0.015/GB/month; R2 IA $0.01/GB/month; IA retrieval $0.01/GB

## Lifecycle Rule Configuration

```toml
# wrangler.toml — lifecycle rules via R2 bucket metadata
# As of wrangler 3.x, lifecycle is set via CF API; wrangler exposes it in --experimental-r2-lifecycle
[[r2_buckets]]
binding = "ARCHIVE"
bucket_name = "media-archive-prod"
```

```bash
# Configure lifecycle via Cloudflare API (until wrangler surfaces the flag)
curl -s -X PUT \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/media-archive-prod/lifecycle" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "rules": [
      {
        "id": "transition-to-ia-90d",
        "status": "enabled",
        "filter": { "prefix": "uploads/" },
        "transitions": [
          {
            "storageClass": "InfrequentAccess",
            "condition": { "maxAge": 90 }
          }
        ]
      },
      {
        "id": "expire-temp-30d",
        "status": "enabled",
        "filter": { "prefix": "temp/" },
        "expiration": { "maxAge": 30 }
      }
    ]
  }'
```

## Cost Comparison: Always-Hot vs Lifecycle

```
Scenario: 10 TB bucket, 90 % cold (accessed < 1×/month), 10 % warm

Always Standard:
  10,000 GB × $0.015 = $150.00/month

With IA transition after 90 days:
  Warm (1,000 GB Standard):  1,000 × $0.015 = $15.00
  Cold (9,000 GB IA):        9,000 × $0.010 = $90.00
  Monthly total:                               $105.00
  Savings: $45/month, $540/year

Break-even retrieval: $540 / $0.01 per GB = 54,000 GB retrievals/year before
savings disappear — well above expected access for cold archive.
```

## Compliance Audit Worker

```typescript
// src/lifecycle-audit.ts
// Cron: "0 3 * * 0"  (weekly, Sunday 03:00 UTC)

interface AuditResult {
  bucket: string;
  objectKey: string;
  uploadedAt: string;
  agedays: number;
  storageClass: string;
  issue: string;
}

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const TRANSITION_THRESHOLD_DAYS = 90;
    const issues: AuditResult[] = [];
    let cursor: string | undefined;

    do {
      const params = new URLSearchParams({ limit: "1000" });
      if (cursor) params.set("cursor", cursor);

      // R2 list via fetch (Workers R2 binding list is simpler)
      const listed = await env.ARCHIVE.list({
        limit: 1000,
        cursor,
        include: ["customMetadata", "httpMetadata"],
      });

      for (const obj of listed.objects) {
        const uploadedAt = obj.uploaded;
        const ageDays = (Date.now() - uploadedAt.getTime()) / 86_400_000;

        // R2 JS binding doesn't expose storageClass directly;
        // use httpMetadata.cacheControl as a proxy, or CF API for accurate class.
        if (ageDays > TRANSITION_THRESHOLD_DAYS) {
          // Flag objects that should be IA but may not be
          // (lifecycle engine lag can be up to 24 h)
          const needsReview = ageDays > TRANSITION_THRESHOLD_DAYS + 2;
          if (needsReview) {
            issues.push({
              bucket: "media-archive-prod",
              objectKey: obj.key,
              uploadedAt: uploadedAt.toISOString(),
              agedays: Math.floor(ageDays),
              storageClass: "UNKNOWN",
              issue: `Object ${ageDays.toFixed(0)}d old, expected IA transition at ${TRANSITION_THRESHOLD_DAYS}d`,
            });
          }
        }
      }

      cursor = listed.truncated ? listed.cursor : undefined;
    } while (cursor);

    // Persist audit results to D1
    if (issues.length > 0) {
      const stmt = env.DB.prepare(
        `INSERT OR REPLACE INTO lifecycle_audit_issues
         (bucket, object_key, uploaded_at, age_days, storage_class, issue, checked_at)
         VALUES (?, ?, ?, ?, ?, ?, datetime('now'))`
      );
      const batch = issues.map((i) =>
        stmt.bind(i.bucket, i.objectKey, i.uploadedAt, i.agedays, i.storageClass, i.issue)
      );
      await env.DB.batch(batch);

      // Alert if issue count is high
      if (issues.length > 100) {
        await fetch(env.ALERT_WEBHOOK, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: `R2 lifecycle audit: ${issues.length} objects may not have transitioned to IA`,
          }),
        });
      }
    }
  },
};
```

## Restore Patterns

```typescript
// R2 IA retrieval is immediate — no restore step needed
// Standard fetch pattern works for both Standard and IA objects

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const key = url.pathname.slice(1);

    const obj = await env.ARCHIVE.get(key);
    if (!obj) return new Response("Not Found", { status: 404 });

    // Optionally re-cache hot-retrieved IA objects in Standard by copying
    if (req.headers.get("X-Promote-To-Standard") === "1") {
      await env.ARCHIVE.put(key, obj.body, {
        httpMetadata: obj.httpMetadata,
        customMetadata: { ...obj.customMetadata, promoted: "1" },
      });
    }

    return new Response(obj.body, {
      headers: {
        "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
        "Cache-Control": "private, max-age=3600",
        "X-R2-Object-Age-Days": String(
          Math.floor((Date.now() - obj.uploaded.getTime()) / 86_400_000)
        ),
      },
    });
  },
};
```

## Anti-patterns

- Applying lifecycle rules to the entire bucket root without a prefix filter—temporary upload paths should expire, not transition to IA.
- Expecting immediate transition—R2 lifecycle engine applies rules within 24 h of the condition being met, not at the exact second.
- Using lifecycle expiration to handle GDPR deletions—lifecycle rules are eventually consistent; for compliance deletions call `DELETE` explicitly.
- Archiving multipart-upload incomplete parts—add a separate rule to abort incomplete multipart uploads after 7 days.

## Gotchas

- R2 IA retrieval fees apply per-GET, not per-GB. Small, frequently accessed IA objects can be more expensive than Standard.
- The R2 Workers binding `.list()` does not return `storageClass` in the JS SDK as of 2026; use the Cloudflare REST API for authoritative storage class data.
- Object versioning and lifecycle rules interact: a `DELETE` marker only suppresses the object, it does not trigger lifecycle expiration on previous versions unless `noncurrentVersionExpiration` is also configured.
- Lifecycle rules added after bucket creation apply only to subsequent condition evaluations, not retroactively.

## Verification

```bash
# Get current lifecycle configuration
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/media-archive-prod/lifecycle" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq .

# List objects older than 90 days (bash snippet)
wrangler r2 object list media-archive-prod --prefix uploads/ \
  | jq '.[] | select(.uploaded | fromdateiso8601 < (now - 90*86400))'

# Check audit D1 table
wrangler d1 execute cost-model \
  --command "SELECT COUNT(*), issue FROM lifecycle_audit_issues GROUP BY issue"
```

## Related

- `/documentation/categories/infra/cloudflare-r2-backup-restore-strategy.md`
- `/documentation/categories/infra/aws-s3-lifecycle-policies.md`
- `/documentation/categories/infra/storage-tiering-strategy.md`
- `/documentation/categories/infra/workers-analytics-billing-monitoring.md`

## Sources

- https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- https://developers.cloudflare.com/r2/reference/pricing/
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
