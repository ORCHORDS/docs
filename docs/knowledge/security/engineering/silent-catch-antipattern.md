# silent-catch-antipattern

**Issue:** .catch(() => {}) hides production bugs across entire codebases
**Date:** 2026-08-09
**Repo:** example-org/example-repo at b874bc02
**Author:** the platform team
**Status:** fixed (b874bc02)

## Symptom
Push notifications, audit log entries, R2 file deletions, badge cache invalidations, and rate-limit violation recordings were silently failing in production. No errors appeared in any log. Features appeared to work because the main happy path succeeded, but side effects were broken.

## Root cause
61 instances of `.catch(() => {})` across 24 backend files. Developers added empty catch blocks during initial development to prevent unhandled rejections from crashing the Worker, then never added proper error handling.

Categories:
| Category | Count | Impact |
|---|---|---|
| Push notifications | ~35 | Users don't get notified |
| createNotification | ~8 | Notification records not created |
| invalidateBadgeCache | ~5 | Stale badge counts |
| D1 audit-log inserts | ~5 | No audit trail |
| recordViolation (rate limit) | 3 | Rate limit evasion |
| R2 deletion | 3 | Orphaned files |
| detectMentions | 2 | @ mentions don't notify |

## Fix
Replace every silent catch with a tagged console.error:

```ts
// BEFORE — invisible failure
pushNotification(env, recipientUid, payload).catch(() => {});

// AFTER — failure is logged and traceable
pushNotification(env, recipientUid, payload).catch((err) => {
  console.error("[dm:push]", err);
});
```

Each tag follows the pattern `[module:operation]` for grep-ability in Cloudflare Workers logs.

## Verification
- **CI:** PR #<number> green
- **Live:** Worker logs now show push/notification/cache errors that were previously invisible

## Gotchas
- `.catch(() => {})` is the #1 source of invisible production bugs
- If you genuinely want to swallow an error, add a comment explaining why: `.catch(() => { /* intentional: user deletion may race */ })`
- For fire-and-forget side effects, use `ctx.waitUntil()` with error logging — it doesn't block the response but still surfaces failures
- ESLint rule `no-empty-function` catches some of these but not arrow-function catches

## Related
- `lessons/example project-audit-2026-08.md`
- `patterns/feature-cookbook-monitoring.md`
- `cloudflare/workers-best-practices.md`
