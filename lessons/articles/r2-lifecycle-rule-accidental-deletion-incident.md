# R2 Lifecycle Rule — Accidental Deletion Incident

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

User avatars across the platform began returning 404 errors. The 404s appeared suddenly and affected only accounts that had uploaded an avatar more than 7 days prior. Investigation revealed that an R2 lifecycle rule intended to expire temporary uploads after 7 days had been applied to the wrong bucket prefix — the root prefix `/` instead of `tmp/` — causing all objects older than 7 days, including permanent user avatars, to be silently deleted.

---

## Context

The platform stores two categories of R2 objects in the same bucket:

| Category | Key prefix | Intended retention |
|---|---|---|
| User avatars | `avatars/{user_id}/` | Permanent (until user deletes) |
| Temporary uploads | `tmp/{upload_id}/` | 7 days (expire after processing) |

A lifecycle rule was added to expire temporary uploads after 7 days to prevent unbounded storage growth from abandoned multi-part uploads and unprocessed files. The rule was configured incorrectly:

**Intended rule:**
```json
{
  "prefix": "tmp/",
  "expiration": { "days": 7 }
}
```

**Actual rule applied:**
```json
{
  "prefix": "",
  "expiration": { "days": 7 }
}
```

An empty `prefix` string matches all keys in the bucket. The rule expired every object in the bucket older than 7 days, including permanent user avatars.

**Stack:**
- Cloudflare R2 (object storage)
- Cloudflare Workers (avatar upload and serve handler)
- R2 lifecycle rules (configured via Wrangler / API)
- Daily R2 export to a separate archival R2 bucket (the recovery path)

---

## Incident Timeline

### 2026-06-01 — Rule Created (incorrect)

- `10:14 UTC` — Engineer adds lifecycle rule via `wrangler r2 bucket lifecycle add` with an empty prefix (UI defaulted to no prefix when the `tmp/` field was left blank).
- `10:15 UTC` — Rule takes effect. Objects in the bucket younger than 7 days are unaffected.

### 2026-06-08 — First deletions begin

- R2 lifecycle engine runs its daily expiration pass. All objects older than 7 days — including user avatars uploaded before 2026-06-01 — are marked for deletion.
- No alert fires: R2 does not emit a lifecycle deletion event count by default to Analytics Engine.

### 2026-06-09 — Detection

- `08:45 UTC` — On-call engineer notices a spike in HTTP 404 responses on the avatar CDN route in the Workers error dashboard.
- `08:52 UTC` — Sample of 404 URLs all follow the pattern `avatars/{user_id}/profile.jpg`.
- `09:01 UTC` — R2 bucket inspection: `avatars/` prefix objects are missing for accounts created before 2026-06-01.
- `09:08 UTC` — Lifecycle rule audit: rule found with empty prefix and 7-day expiration. Rule created 2026-06-01.
- `09:15 UTC` — Lifecycle rule deleted immediately.

### 2026-06-09 — Recovery

- `09:20 UTC` — Archival bucket (daily export) confirmed to have avatars from the 2026-06-08 snapshot.
- `09:45 UTC` — Recovery Worker deployed: copies missing avatar keys from archival bucket back to production bucket.
- `11:30 UTC` — Recovery complete. Avatar 404 rate returns to baseline.
- `12:00 UTC` — Post-incident review scheduled.

---

## Root Cause

The R2 lifecycle rule was applied with an empty prefix, which in R2's lifecycle semantics matches all keys in the bucket. The Wrangler CLI and API both accept an empty string as a valid prefix — it is not an error — but its meaning ("match everything") is not surfaced as a warning in the tooling.

The engineer configuring the rule intended to scope it to `tmp/` objects but did not realize the prefix field had been left blank. No review step verified the applied rule before it took effect.

Additionally:
- The bucket stored both ephemeral and permanent assets, violating the principle of separation.
- There was no alert on lifecycle deletion volume.
- Recovery was possible only because of the daily archival export — a safeguard that was in place but not designed for this specific scenario.

---

## Recovering Deleted Objects

R2 does not have object versioning (at time of incident). Once a lifecycle rule deletes an object, it is unrecoverable from R2 itself. Recovery depended entirely on the external archival bucket:

```typescript
// recovery-worker/src/index.ts
// Run once as a one-shot Worker to copy missing avatars from archival bucket

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    let cursor: string | undefined;
    let restored = 0;

    do {
      const list = await env.ARCHIVAL_BUCKET.list({
        prefix: 'avatars/',
        cursor,
        limit: 1000,
      });

      for (const obj of list.objects) {
        // Check if object is missing from production bucket
        const existing = await env.PROD_BUCKET.head(obj.key);
        if (!existing) {
          // Copy from archival to production
          const body = await env.ARCHIVAL_BUCKET.get(obj.key);
          if (body) {
            await env.PROD_BUCKET.put(obj.key, body.body, {
              httpMetadata: body.httpMetadata,
              customMetadata: body.customMetadata,
            });
            restored++;
          }
        }
      }

      cursor = list.truncated ? list.cursor : undefined;
    } while (cursor);

    return new Response(`Restored ${restored} objects.`);
  }
};
```

---

## Fix and Prevention Measures

### 1. Scoped Lifecycle Rule (immediate fix)

```json
{
  "prefix": "tmp/",
  "expiration": { "days": 7 }
}
```

Rule verified with `wrangler r2 bucket lifecycle list --bucket production-assets` before considering the fix complete.

### 2. Separate Buckets for Ephemeral vs Permanent Assets

This was the highest-impact structural change:

| Bucket | Contents | Lifecycle rule |
|---|---|---|
| `production-avatars` | User avatars, permanent media | No lifecycle rule |
| `production-tmp` | Temporary uploads, processing artifacts | 7-day expiration on `/` |

Separating buckets means a misconfigured lifecycle rule on `production-tmp` can only affect temporary files. Permanent assets are structurally protected.

```toml
# wrangler.toml
[[r2_buckets]]
binding = "AVATAR_BUCKET"
bucket_name = "production-avatars"

[[r2_buckets]]
binding = "TMP_BUCKET"
bucket_name = "production-tmp"
```

### 3. Cron Worker — Weekly Lifecycle Rule Audit

A Cron Worker runs every Monday at 06:00 UTC and audits all lifecycle rules across all production R2 buckets. It alerts if any rule has an empty prefix on a bucket that contains non-ephemeral data:

```typescript
// cron-workers/r2-lifecycle-audit.ts
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    const buckets = [
      { name: 'production-avatars', allowLifecycle: false },
      { name: 'production-assets', allowLifecycle: false },
      { name: 'production-tmp', allowLifecycle: true },
    ];

    const findings: string[] = [];

    for (const bucket of buckets) {
      const rules = await listLifecycleRules(bucket.name, env);

      if (!bucket.allowLifecycle && rules.length > 0) {
        findings.push(
          `ALERT: Lifecycle rule found on non-ephemeral bucket "${bucket.name}": ${JSON.stringify(rules)}`
        );
      }

      for (const rule of rules) {
        if (rule.prefix === '' || rule.prefix === '/') {
          findings.push(
            `ALERT: Lifecycle rule with empty prefix on bucket "${bucket.name}" — matches ALL objects`
          );
        }
      }
    }

    if (findings.length > 0) {
      await sendAlert(findings.join('\n'), env);
    }
  }
};
```

### 4. R2 Deletion Volume Alert

A Tail Worker now emits a data point whenever the platform successfully deletes an R2 object (user-initiated deletes). A separate Analytics Engine alert fires if R2 object count in `production-avatars` drops by more than 1% in a 24-hour window without a corresponding bulk-delete operation being logged:

```typescript
// Rough approximation: monitor object count via R2 list + Analytics Engine
// A sudden drop in object count without a matching admin action is suspicious
```

---

## Anti-patterns / What Went Wrong

1. **Mixing ephemeral and permanent assets in the same R2 bucket.** A lifecycle rule on a mixed bucket is always a misconfiguration risk. Keep ephemeral and permanent assets in separate buckets.

2. **No review of applied lifecycle rules before relying on them.** The engineer added the rule and moved on. A `wrangler r2 bucket lifecycle list` verification step was not part of the workflow.

3. **Empty prefix not validated as a warning by tooling.** `prefix: ""` is a footgun. Tooling should warn, but it does not. Engineers must know that an empty prefix matches everything.

4. **No deletion volume monitoring on R2.** If a metric had tracked total object count or delete operations per day, the mass deletion on 2026-06-08 would have fired an immediate alert rather than being discovered via 404 spikes the next morning.

5. **Recovery depended on an unplanned side-effect.** The daily archival export was in place for compliance reasons, not as a disaster recovery mechanism. Recovery worked, but it was not a designed and tested process.

---

## Gotchas

- **R2 lifecycle rules with `prefix: ""` match all keys.** This is the same behavior as S3. An empty prefix is not "no rule" — it is "all objects."
- **R2 does not have native object versioning at time of writing.** Unlike S3 versioning, there is no built-in "undelete" for R2 lifecycle deletions. External archival is the only recovery path.
- **Lifecycle rules take effect within 24 hours but the exact timing is not guaranteed.** You cannot predict the exact moment objects are deleted; monitoring must catch anomalies after the fact.
- **`wrangler r2 bucket lifecycle add` accepts an empty prefix without error.** Always run `lifecycle list` after adding a rule to confirm what was actually applied.
- **Separate buckets for different retention classes is the standard pattern.** AWS well-architected guidance, GCP guidance, and Cloudflare all recommend this. The cost of an extra bucket binding is zero.

---

## Verification

- Avatar 404 rate: returned to baseline within 2 hours of recovery Worker completion.
- Object count in `production-avatars`: confirmed stable at expected value post-separation.
- Lifecycle audit Cron Worker: confirmed running weekly, zero findings in first 4 weeks.
- Disaster recovery runbook updated: `docs/runbooks/r2-recovery.md` documents the archival copy procedure.
- Post-incident test: intentionally misconfigure a rule on the staging `production-tmp` bucket with empty prefix, confirm audit Cron Worker fires alert within 7 days.

---

## Related

- `durable-objects-alarm-delivery-guarantee-lesson.md`
- `workers-cold-start-regression-silent-deploy-postmortem.md`
- Cloudflare R2: [Object lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- Cloudflare R2: [Buckets overview](https://developers.cloudflare.com/r2/buckets/)

---

## Sources

- Internal incident report `INC-2026-0609`
- R2 bucket lifecycle rule audit output
- Recovery Worker execution log
- Post-incident architecture review notes
- `docs/adr/ADR-2026-009.md` — R2 bucket separation policy
