# R2 Lifecycle Rule Overwrote Active Data Incident

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

After an infrastructure engineer applied a new R2 lifecycle rule intended to delete audio
recordings older than 90 days in a "cold archive" bucket, a misconfigured rule prefix caused
the deletion to target the active production bucket instead. Within 6 hours of the rule being
applied, Cloudflare's lifecycle processor began deleting objects whose `Last-Modified` timestamp
was older than 90 days — including the original master audio files for 3 400 active example project
(example.com) projects. The objects were permanently deleted with no soft-delete layer, no
versioning, and no backup. Users began reporting "File not found" errors when attempting to
re-export or re-process their projects.

The incident cost the team approximately 180 hours of engineering time for impact assessment,
user communication, and partial recovery from a 72-hour-old backup snapshot. It directly
triggered a product-wide adoption of R2 object versioning and a formal change management
policy for bucket lifecycle modifications.

## Context

Cloudflare R2 provides S3-compatible object storage with a lifecycle rules engine. Lifecycle
rules can expire (delete) objects based on age relative to `Last-Modified`. Unlike AWS S3,
R2 did not support object versioning at the time of the incident (versioning has since been
added in beta); once an object was deleted by a lifecycle rule, it was unrecoverable from the
R2 layer.

example project used two R2 buckets: `wam-audio-prod` (active project files, no expiry intended)
and `wam-audio-archive` (cold storage for projects closed more than 90 days). The incident
engineer intended to apply a lifecycle rule only to `wam-audio-archive` but applied it to
`wam-audio-prod` due to a copy-paste error in the Wrangler config and the absence of a bucket
name confirmation prompt in the apply workflow.

## Timeline

**08:30 UTC** — Infrastructure engineer prepares lifecycle rule for the archive bucket:

```json
{
  "rules": [{
    "id": "delete-old-archives",
    "status": "Enabled",
    "filter": { "prefix": "" },
    "expiration": { "days": 90 }
  }]
}
```

**08:35 UTC** — Engineer runs `wrangler r2 bucket lifecycle set wam-audio-prod ...` instead
of `wam-audio-archive`. No confirmation prompt. Command succeeds silently.

**08:36 UTC** — Cloudflare lifecycle processor begins scanning `wam-audio-prod` for objects
older than 90 days. Deletions are not logged to Logpush by default.

**14:00 UTC** — First user reports: "My project files are gone." Support ticket opened.

**14:30 UTC** — Second and third reports arrive. On-call engineer investigates; no recent code
deploy. Checks R2 bucket stats — object count has dropped from ~420 000 to ~391 000.

**15:00 UTC** — Engineer lists lifecycle rules on `wam-audio-prod` and discovers the rule.

**15:02 UTC** — Rule is deleted via `wrangler r2 bucket lifecycle delete wam-audio-prod`.
Lifecycle processing stops. ~29 000 objects have already been deleted.

**15:05 UTC** — Engineering team begins impact scoping. Cross-references deleted object keys
with the D1 projects table to identify affected users.

**Day 2, 10:00 UTC** — Partial recovery completed by restoring a 72-hour-old snapshot of
`wam-audio-prod` from a secondary cold backup (a separate R2 bucket with weekly snapshots).
Objects created or modified in the 72-hour window before the incident and then deleted are
unrecoverable.

## Root Cause Analysis

Three independent failures compounded:

**1. Wrong bucket name in CLI command.** The engineer had both bucket names in a terminal
buffer. The wrong name was pasted. Wrangler does not prompt for confirmation when applying
lifecycle rules that affect all objects (empty prefix).

**2. Empty prefix = all objects.** The lifecycle rule used `"prefix": ""`, which matches
every object in the bucket. A scoped prefix (`archive/`) would have limited blast radius.

**3. No object versioning or soft-delete.** The production bucket had no versioning enabled,
so lifecycle-deleted objects were immediately unrecoverable.

The misconfigured wrangler command:

```bash
# Intended target: wam-audio-archive
# Actual command run: wam-audio-prod
wrangler r2 bucket lifecycle set wam-audio-prod \
  --lifecycle-config-file ./lifecycle-archive.json
```

The lifecycle config had no scoping prefix, so every object in the bucket aged > 90 days was
eligible for deletion:

```json
{
  "rules": [{
    "id": "delete-old-archives",
    "status": "Enabled",
    "filter": { "prefix": "" },
    "expiration": { "days": 90 }
  }]
}
```

The correct configuration for the archive bucket would have been:

```json
{
  "rules": [{
    "id": "delete-old-archives",
    "status": "Enabled",
    "filter": { "prefix": "archived/" },
    "expiration": { "days": 90 }
  }]
}
```

## Impact Analysis

- 29 000 objects permanently deleted from the production bucket.
- 3 400 active example project projects affected; of those, 412 had audio files created or modified
  within 72 hours and were unrecoverable from backup.
- 412 users received prorated refunds and a complimentary 3-month subscription extension.
- Engineering time: 180 hours across incident response, recovery, and user communication.
- Estimated direct financial cost: ~$42 000 (refunds, credits, engineering overhead).
- Reputational impact: incident was publicly discussed on social media by several affected users.

## Remediation

### Enable R2 object versioning (post-incident)

With versioning enabled, lifecycle expiration moves objects to a "noncurrent" state rather than
permanently deleting them. A second, longer-TTL rule can be applied to noncurrent versions:

```json
{
  "rules": [
    {
      "id": "expire-current-archive-objects",
      "status": "Enabled",
      "filter": { "prefix": "archived/" },
      "expiration": { "days": 90 }
    },
    {
      "id": "delete-noncurrent-archive-objects",
      "status": "Enabled",
      "filter": { "prefix": "archived/" },
      "noncurrentVersionExpiration": { "noncurrentDays": 30 }
    }
  ]
}
```

```bash
# Enable versioning on the production bucket
wrangler r2 bucket update wam-audio-prod --versioning enabled
```

### Wrangler lifecycle apply wrapper with confirmation

Replace direct `wrangler r2 bucket lifecycle set` calls with a wrapper script that:
1. Prints current rules before overwriting.
2. Diffs the new config against existing rules.
3. Requires explicit `--confirm-bucket=<name>` to prevent wrong-bucket mistakes.

```bash
#!/usr/bin/env bash
# scripts/apply-r2-lifecycle.sh
set -euo pipefail

BUCKET=$1
CONFIG_FILE=$2
CONFIRM_BUCKET=$3

if [[ "$BUCKET" != "$CONFIRM_BUCKET" ]]; then
  echo "ERROR: --confirm-bucket mismatch. Got '$CONFIRM_BUCKET', expected '$BUCKET'."
  exit 1
fi

echo "=== Current lifecycle rules for $BUCKET ==="
wrangler r2 bucket lifecycle list "$BUCKET"

echo ""
echo "=== New lifecycle config to apply ==="
cat "$CONFIG_FILE"

echo ""
read -r -p "Apply lifecycle config to $BUCKET? [yes/NO] " CONFIRM
if [[ "$CONFIRM" != "yes" ]]; then
  echo "Aborted."
  exit 1
fi

wrangler r2 bucket lifecycle set "$BUCKET" --lifecycle-config-file "$CONFIG_FILE"
echo "Lifecycle rules applied to $BUCKET."
```

### Lifecycle rule naming convention enforcing scope

Enforce that every lifecycle rule ID encodes the target bucket prefix, making accidental
all-objects rules visually obvious in review:

```json
{
  "rules": [{
    "id": "wam-audio-archive__prefix-archived__expire-90d",
    "status": "Enabled",
    "filter": { "prefix": "archived/" },
    "expiration": { "days": 90 }
  }]
}
```

A CI lint script rejects rules with an empty prefix on non-archive buckets:

```typescript
// scripts/lint-r2-lifecycle.ts
import { readFileSync } from 'fs';

const ARCHIVE_BUCKET_PATTERN = /archive/i;
const [, , bucketName, configFile] = process.argv;

const config = JSON.parse(readFileSync(configFile, 'utf8'));
for (const rule of config.rules ?? []) {
  const prefix: string = rule.filter?.prefix ?? '';
  if (prefix === '' && !ARCHIVE_BUCKET_PATTERN.test(bucketName)) {
    console.error(
      `FAIL: Rule "${rule.id}" has empty prefix on non-archive bucket "${bucketName}".` +
      ` All lifecycle rules on production buckets must specify a non-empty prefix.`
    );
    process.exit(1);
  }
}
console.log('Lifecycle config lint passed.');
```

## Prevention

- **Enable versioning on all production R2 buckets** before applying any lifecycle rules.
- **Require two-person review** for any lifecycle rule changes via a Terraform/IaC change request
  rather than direct `wrangler` CLI invocation.
- **Never use empty prefix `""` on production buckets** — always scope rules to a key prefix
  that semantically matches the data category being expired.
- **Enable R2 Logpush for object deletions** so lifecycle deletions are auditable in real time.
- **Test lifecycle rules in a staging bucket** with synthetic data before applying to production.

## Anti-patterns

- Applying lifecycle rules directly via CLI without a confirmation step or change record.
- Using `"prefix": ""` (all objects) on production buckets without versioning enabled.
- Managing two similar bucket names in the same workflow without explicit bucket name confirmation.
- Treating R2 lifecycle deletion as reversible without having versioning or backup in place.
- Omitting R2 object deletion events from observability/alerting pipelines.

## Gotchas

- R2 lifecycle rules take effect asynchronously — there is no preview or dry-run mode. Once
  applied with an empty prefix, deletions begin within hours.
- `wrangler r2 bucket lifecycle set` replaces all existing rules atomically; it does not merge
  with existing rules.
- Lifecycle rules process `Last-Modified` time, not object creation time. An object re-uploaded
  with the same key resets the clock; an object never touched since initial upload accumulates age.
- R2 does not generate an S3-compatible `s3:LifecycleExpiration` event notification by default.
  Object deletion events require R2 Event Notifications with an explicit lifecycle filter.
- Cloudflare support cannot recover R2 objects deleted by lifecycle rules (confirmed by support
  engineering in incident ticket).

## Verification

```bash
# 1. Confirm versioning is enabled on the production bucket
wrangler r2 bucket info wam-audio-prod | grep -i versioning

# 2. List all lifecycle rules (should show scoped prefixes only)
wrangler r2 bucket lifecycle list wam-audio-prod

# 3. Verify a test object can be recovered after deletion with versioning enabled
wrangler r2 object put wam-audio-prod/test-versioning.txt --file /dev/stdin <<< "test"
wrangler r2 object delete wam-audio-prod/test-versioning.txt
# List noncurrent versions:
wrangler r2 object list wam-audio-prod --prefix test-versioning.txt --versions

# 4. Confirm Event Notifications are configured for deletions
wrangler r2 bucket notification list wam-audio-prod
```

## Related

- `r2-event-notification-missed-fires-postmortem.md`
- `r2-presigned-url-race-condition-upload-incident.md`
- `never-delete-without-soft-delete-first.md`
- `test-your-backups-not-just-your-backup-process.md`

## Sources

- Cloudflare R2 lifecycle rules documentation: https://developers.cloudflare.com/r2/buckets/object-lifecycles/
- Cloudflare R2 versioning documentation: https://developers.cloudflare.com/r2/buckets/versioning/
- Cloudflare R2 event notifications: https://developers.cloudflare.com/r2/buckets/event-notifications/
