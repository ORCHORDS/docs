# R2 bucket lock retention precedence

**Issue:** Lifecycle deletion is expected to remove an R2 object that is still covered by a bucket lock, or a removable bucket-lock rule is mistaken for an immutable legal-hold system.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define narrow, reviewed prefixes and retention conditions before enabling a lock rule.
- Model duration, retain-until date, and indefinite rules separately; when several rules match, the strictest and longest requirement wins.
- Treat bucket locks as taking precedence over lifecycle deletion and apply that interaction to both existing and new objects.
- Restrict and audit the API token or administrator authority that can change lock configuration.
- Keep regulatory legal-hold decisions, evidence ownership, and retention approvals outside application code.
- Inventory lock rules before attempting to empty or delete a bucket.

## Verification

Create overlapping prefix rules, overwrite and delete covered objects, run the lifecycle boundary, and verify retention until the longest applicable condition expires. Test that bucket emptying is blocked while rules remain.

## Gotchas

Rules may be removed by authorized configuration changes, so operational bucket locks alone do not prove immutable WORM compliance. A bucket cannot be emptied while any lock rule is configured.

## Official sources

- [Cloudflare R2 bucket locks](https://developers.cloudflare.com/r2/buckets/bucket-locks/)
