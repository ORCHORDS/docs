# R2 Bucket Name Typo Production Data Loss Near-Miss

Date: 2026-08-23 / Author: example.com / Status: production

---

## Incident Summary

On 2026-03-11 an engineer provisioning a new R2 bucket for a staging environment
mistyped the bucket name as `tracks-uploads-prod` instead of the intended
`tracks-uploads-stg`. A misconfigured Worker binding then routed production audio
upload traffic to the staging-named bucket for 4 hours and 12 minutes. No data was
permanently lost because the erroneous bucket retained all uploaded objects, but the
incident exposed three systemic failures: no bucket-naming convention enforcement,
no binding validation before deploy, and no alarm on unexpected bucket creation in
production accounts.

---

## Context

- Cloudflare account: `orchords-production` (separate from `orchords-staging`)
- Intended new bucket: `tracks-uploads-stg` (staging environment)
- Accidentally created bucket: `tracks-uploads-prod` (production environment)
- R2 bindings affected: `TRACKS_UPLOAD_BUCKET` in the `audio-ingest` Worker
- Upload volume during incident window: ~18 000 objects, ~340 GB
- User-visible symptom: none during the incident (uploads succeeded to wrong bucket)
- Detection: scheduled data-integrity job comparing object counts between R2 and D1
  metadata records, which fired 4 hours after the incident started

---

## Timeline

**09:14 UTC** — Engineer creates a new R2 bucket via `wrangler r2 bucket create`. The
command is run in a terminal that has the production Cloudflare account token set in
`CLOUDFLARE_API_TOKEN`. The intended command was:
```bash
wrangler r2 bucket create tracks-uploads-stg
```
But the typed command was:
```bash
wrangler r2 bucket create tracks-uploads-prod
```
`wrangler` succeeds silently. The bucket is created in the production account.

**09:17 UTC** — Engineer updates `wrangler.toml` for the `audio-ingest` Worker,
intending to add the staging binding. Due to a copy-paste error, the binding is added
to the production environment block instead of the staging block:

```toml
[env.production.r2_buckets]  # WRONG — should be [env.staging.r2_buckets]
[[env.production.r2_buckets]]
binding = "TRACKS_UPLOAD_BUCKET"
bucket_name = "tracks-uploads-prod"  # accidentally matches the typo bucket
```

**09:19 UTC** — `wrangler deploy --env production` succeeds. The production Worker now
binds to `tracks-uploads-prod` (the typo bucket) instead of the original
`tracks-uploads` bucket.

**09:20 UTC** — Production audio upload traffic begins writing to `tracks-uploads-prod`.

**13:32 UTC** — Scheduled data-integrity cron job runs. It queries D1 for all upload
records created in the past 4 hours and checks that each `r2_key` exists in the
`tracks-uploads` bucket. ~18 000 keys are missing. Alert fires.

**13:38 UTC** — On-call engineer investigates. Discovers uploads are in
`tracks-uploads-prod`, not `tracks-uploads`. Corrects the `wrangler.toml` binding and
redeploys.

**13:42 UTC** — Production Worker rebinds to `tracks-uploads`. New uploads route
correctly.

**13:55 UTC** — Backfill script copies all 18 000 objects from `tracks-uploads-prod`
to `tracks-uploads` using R2 server-side copy API.

**14:10 UTC** — Backfill complete. D1 integrity check passes. Incident closed.

**14:30 UTC** — `tracks-uploads-prod` bucket is retained (not deleted) pending
post-incident review. Eventually quarantined.

---

## Root Cause

### Primary: No account-context guard on wrangler CLI

The engineer's shell had `CLOUDFLARE_API_TOKEN` set to the production account token.
There was no environment variable, shell alias, or wrapper script that would warn or
block `wrangler` commands targeting the production account from a terminal session
intended for staging work.

### Secondary: `wrangler.toml` production and staging blocks in the same file

Having both `[env.production]` and `[env.staging]` blocks in the same `wrangler.toml`
makes copy-paste errors between environments easy. The TOML diff was small and the
review did not catch the wrong environment block.

### Tertiary: No bucket-binding verification step in CI

The deploy pipeline ran `wrangler deploy` without any pre-deploy check that confirmed
the R2 bucket names in the binding matched an allow-list of expected bucket names for
each environment.

---

## Fix (Immediate)

1. Correct `wrangler.toml` binding to reference the original `tracks-uploads` bucket.
2. Redeploy the production Worker.
3. Run backfill to copy objects from the typo bucket to the correct bucket.
4. Verify D1 integrity check passes.

---

## Fix (Structural)

### 1. Enforce bucket naming convention via a pre-deploy CI check

```bash
#!/bin/bash
# check-r2-bindings.sh
ENVIRONMENT=$1
TOML_BUCKET=$(wrangler r2 bucket list --json | jq -r '.[] | .name')

# Allow-list per environment
case "$ENVIRONMENT" in
  production)
    ALLOWED_BUCKETS="tracks-uploads tracks-assets-prod"
    ;;
  staging)
    ALLOWED_BUCKETS="tracks-uploads-stg tracks-assets-stg"
    ;;
esac

for bucket in $(grep 'bucket_name' wrangler.toml | awk -F'"' '{print $2}'); do
  if ! echo "$ALLOWED_BUCKETS" | grep -q "$bucket"; then
    echo "ERROR: Bucket '$bucket' not in allow-list for environment '$ENVIRONMENT'"
    exit 1
  fi
done
echo "All R2 bucket bindings validated."
```

Add this check to the CI pipeline before `wrangler deploy`.

### 2. Separate `wrangler.toml` per environment

Instead of one file with `[env.production]` and `[env.staging]` blocks, maintain
separate files:

```
workers/audio-ingest/
  wrangler.production.toml
  wrangler.staging.toml
```

Deploy commands become:
```bash
wrangler deploy --config wrangler.production.toml   # requires explicit file
wrangler deploy --config wrangler.staging.toml
```

This makes it impossible to accidentally deploy staging config to production via a
copy-paste in TOML.

### 3. Use different Cloudflare account tokens per environment

```bash
# ~/.bashrc / ~/.zshrc
alias wrangler-prod='CLOUDFLARE_API_TOKEN=$CF_PROD_TOKEN wrangler'
alias wrangler-stg='CLOUDFLARE_API_TOKEN=$CF_STG_TOKEN wrangler'
```

The production token should require a second factor or hardware key approval via
Cloudflare Access for any CLI operation that modifies resources. Alternatively, use
separate Cloudflare accounts (already the case here, but not enforced at the CLI level).

### 4. Add R2 bucket creation alerts

Use Cloudflare Audit Logs (via Logpush to R2 + an alerting Worker) to detect any
new R2 bucket creation in the production account:

```ts
// audit-log-monitor Worker
if (event.action === 'r2.bucket.create' && event.account === PROD_ACCOUNT_ID) {
  await sendSlackAlert(`New R2 bucket created in PROD: ${event.resource_name}`);
}
```

This provides a real-time signal for unexpected resource creation.

### 5. Implement R2 bucket tagging and verify tags in pre-deploy checks

Tag buckets at creation time with `environment=production` or `environment=staging`.
Pre-deploy checks can query bucket tags to confirm environment alignment.

---

## Prevention

- **Never use production API tokens in a terminal session intended for staging work.**
  Separate shell profiles, separate terminal profiles, or mandatory 2FA for production
  API operations.
- **Bucket naming conventions must be machine-enforced**, not style-guide suggestions.
  A CI check that fails the deploy pipeline on unexpected bucket names takes seconds
  to add and prevents this entire class of incident.
- **Data-integrity checks are a critical last line of defence** — but their value
  depends on how quickly they run after data flows to the wrong location. Consider
  running integrity checks every 15 minutes for high-value upload flows.
- **Audit log alerting for production resource creation** provides an early warning
  independent of any application-level monitoring.

---

## Anti-patterns

- **One `wrangler.toml` with both production and staging environment blocks:** The
  shared file is a copy-paste trap. Small TOML diffs are easy to miss in PR review.
- **Silent success from `wrangler r2 bucket create` with a name that matches no
  known bucket in the intended environment:** The CLI has no way to know your
  intent, but your CI pipeline can.
- **Relying on application-level error rates to detect wrong-bucket routing:** If the
  wrong bucket accepts writes successfully (because it exists), the application sees
  no errors and no alerts fire.
- **Deleting the typo bucket immediately during an incident:** Objects may still be
  in-flight to the wrong bucket. Quarantine first, verify, then delete after the
  backfill is confirmed complete.

---

## Gotchas

- R2 does not support server-side copy between buckets via the S3-compatible API's
  `x-amz-copy-source` header when the source and destination are in different buckets.
  Use the Workers R2 binding's `put(key, await src_bucket.get(key).body)` pattern or
  the R2 migration tool for large-scale copies.
- R2 bucket names are globally unique within an account. A typo bucket name that
  happens to already exist will fail with `BucketAlreadyExists`, which is a different
  failure mode — but equally confusing.
- Cloudflare R2 does not natively support bucket-level IAM policies that restrict which
  Workers can bind to a given bucket. Enforcement must be done at the `wrangler.toml`
  / CI level.
- Object versioning is not enabled by default on R2 buckets. A `put()` to an existing
  key overwrites the object permanently. In this incident, the typo bucket did not
  have naming conflicts, so no data was overwritten — but this might not be the case
  in other scenarios.

---

## Verification

1. Confirm the post-incident CI check is running: open a staging-only PR and verify
   the check passes with staging bucket names and fails when a production bucket name
   is inserted.
2. Confirm Audit Log alerting fires within 60 seconds of a test bucket creation in
   the production account. Delete the test bucket immediately after.
3. Confirm the backfill is complete: D1 integrity check must pass for all 18 000
   object keys.
4. Confirm `tracks-uploads-prod` typo bucket is quarantined (access policy locked)
   and scheduled for deletion after the 30-day retention window.

---

## Related

- `r2-lifecycle-rule-active-data-overwrite-incident.md`
- `r2-event-notification-missed-fires-postmortem.md`
- `kv-namespace-deleted-wrong-environment-postmortem.md`
- `never-delete-without-soft-delete-first.md`
- `silent-data-loss-partial-writes.md`

---

## Sources

- Cloudflare R2 documentation: https://developers.cloudflare.com/r2/
- Cloudflare Audit Logs: https://developers.cloudflare.com/fundamentals/account/account-security/review-audit-logs/
- Wrangler CLI environment documentation: https://developers.cloudflare.com/workers/wrangler/environments/
- Internal postmortem ticket PM-2026-014 (restricted)
