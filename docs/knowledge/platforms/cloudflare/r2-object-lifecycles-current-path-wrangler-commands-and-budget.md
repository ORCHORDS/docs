# r2-object-lifecycles-current-path-wrangler-commands-and-budget

**Issue:** R2 object lifecycles — canonical current path, Wrangler command set, rule budget, default multipart abort, and storage-class transition target
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

Corpus has at least one older md that references the **singular** path `developers.cloudflare.com/r2/buckets/object-lifecycle/` (no trailing `s`) and predates the Wrangler CLI gaining first-class R2 lifecycle subcommands. Other mds describe lifecycles as API-only ("Not yet available via wrangler CLI"), which is stale. A team trying to set or list lifecycle rules hits a 404 on the old path and has no canonical reference for the Wrangler command shape.

## Root cause

Cloudflare's R2 docs moved the lifecycle reference page from singular `object-lifecycle` to **plural `object-lifecycles`** and shipped first-class Wrangler support in `wrangler r2 bucket lifecycle …`. Verified 2026-10-03 against `https://developers.cloudflare.com/r2/buckets/object-lifecycles/index.md` (HTML `dateModified: 2026-04-21`).

## Canonical surface (verified)

- Doc URL: `https://developers.cloudflare.com/r2/buckets/object-lifecycles/` (plural, with trailing `s`)
- Page `dateModified`: **2026-04-21**
- Configurable rule actions: **Expire objects** (current and noncurrent versions), **Transition to Infrequent Access storage class** (target: **`STANDARD_IA`**), **Abort incomplete multipart uploads** (default applies after 7 days)
- Default rule: every R2 bucket has a default 7-day multipart-upload abort rule. To keep incomplete uploads longer, add an explicit rule that overrides the default.
- **Maximum 1000 lifecycle rules per bucket.**
- API token permission required to mutate lifecycles via the REST API: `Workers R2 Storage Write` (object write alone is not sufficient).

## Wrangler CLI (first-class, verified)

```bash
# Add a rule (interactive prompts)
wrangler r2 bucket lifecycle add <bucket-name>

# List rules in JSON
wrangler r2 bucket lifecycle list <bucket-name>

# Remove a rule by ID
wrangler r2 bucket lifecycle remove <bucket-name>

# Replace all rules in one shot from a JSON file
wrangler r2 bucket lifecycle set <bucket-name> --rules ./lifecycle.json
```

`wrangler r2 bucket lifecycle …` is the supported path for everyday work; the REST API (`PUT /accounts/{account_id}/r2/buckets/{bucket_name}/lifecycle`) and the S3-compatible `PutBucketLifecycleConfiguration` are still valid for programmatic / multi-bulk orchestration.

## S3-compatible API shape (for tools that expect it)

```xml
<LifecycleConfiguration>
  <Rule>
    <ID>expire-temp-uploads</ID>
    <Status>Enabled</Status>
    <Filter><Prefix>tmp/</Prefix></Filter>
    <Expiration><Days>1</Days></Expiration>
  </Rule>
</LifecycleConfiguration>
```

Storage-class transitions to `STANDARD_IA` use the same `Rule` block with a `<Transition><StorageClass>STANDARD_IA</StorageClass><Days>30</Days></Transition>` child element. Cloudflare's R2 ignores unsupported XML elements (S3 `<Glacier*>` etc.) silently — validate with `wrangler r2 bucket lifecycle list` after `set`.

## Gotchas

- The default 7-day multipart abort applies automatically; **opt out** by adding an explicit abort rule with a longer (or no) `Days` value. Confirmed on current page.
- Rule IDs are unique per bucket. Re-running `set` with duplicate IDs is rejected.
- Lifecycle evaluation is eventual (not synchronous to `put`); allow several minutes for the first cycle on a populated bucket.
- 1000 rules per bucket is a hard cap — partition very large rule sets by prefix to stay under it.

## Verification

- **Live page:** `https://developers.cloudflare.com/r2/buckets/object-lifecycles/` → 200 OK, dateModified 2026-04-21
- **Wrangler help:** `wrangler r2 bucket lifecycle --help` lists `add` / `list` / `remove` / `set`
- **API:** `curl -fsS -X PUT "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/$BUCKET/lifecycle" -H "Authorization: Bearer $CF_API_TOKEN" -d @rules.json` → 200 OK

## Related / supersedes

- `docs/knowledge/platforms/cloudflare/cloudflare-r2-lifecycle-auto-delete.md` — references `r2/buckets/object-lifecycles/` (already plural), needs cross-check on Wrangler-vs-API claims
- `docs/knowledge/platforms/cloudflare/cloudflare-r2-object-lifecycle-multipart.md` — covers the default-7-day multipart abort, can be cross-linked
- `docs/knowledge/platforms/cloudflare/r2-lifecycle-rules.md` and `docs/knowledge/platforms/cloudflare/r2-lifecycle-rules-storage-tiers.md` — older mds, may still claim "API only" / "not yet via wrangler CLI"; verify against the new CLI subcommands before referencing
- 0 corpus mds use the singular `object-lifecycle` path today (verified `grep -rln '/r2/buckets/object-lifecycle[^s]'` → empty)