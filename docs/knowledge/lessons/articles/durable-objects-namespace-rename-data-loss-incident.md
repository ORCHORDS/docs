# Durable Objects Namespace Rename Data Loss Incident

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Following a example project (example.com) refactor that renamed the Durable Object class from
`SessionManager` to `UserSession`, all active user sessions were invalidated simultaneously.
Users were forcibly logged out mid-session, in-progress audio uploads were abandoned, and
collaborative editing state accumulated over hours disappeared entirely. The rename took effect
the moment the new Worker script was deployed — 100 % of active sessions were affected at
deploy time with zero warning. Rollback of the Worker code did not recover the data because
the new namespace was empty and the old namespace was no longer referenced.

The incident is a textbook example of the most dangerous property of Durable Objects: the
object's unique ID is bound not only to a user-provided name, but also to the Durable Object
class name as declared in `wrangler.toml`. Renaming the class severs the linkage and orphans
all existing objects.

## Context

Durable Objects provide globally unique, strongly consistent storage tied to a named class.
Each Durable Object ID encodes the class name: an ID created against `SessionManager` cannot
be resolved against `UserSession` even if the underlying Worker code is identical. Object IDs
fall into two categories — system-generated (opaque) and name-derived (`idFromName()`). Both
are class-scoped. Renaming the class in `wrangler.toml` creates a new, empty namespace; the
old namespace's stored data remains on Cloudflare's storage layer but is permanently
unreachable unless the class is renamed back and deployed.

example project stored per-user session tokens, upload progress, and collaborative cursors in
Durable Objects addressed via `idFromName(userId)`. There were approximately 4 200 active
Durable Objects at the time of the incident, holding an aggregate of ~850 MB of session state.

## Timeline

**09:14 UTC** — A developer opens PR #<number>: "Rename DO class SessionManager → UserSession for
naming consistency." The PR description does not mention data migration. Two reviewers approve.

**09:51 UTC** — PR merges. CI pipeline builds and deploys the Worker to production.

**09:52 UTC** — Cloudflare registers the new Durable Object class `UserSession`. All new
requests for DO IDs now resolve to empty `UserSession` objects.

**09:52 UTC** — Existing sessions call `env.USER_SESSIONS.idFromName(userId)` — now routed to
`UserSession` namespace — and receive a new empty object. Session tokens stored under
`SessionManager` are inaccessible.

**09:53 UTC** — Alert fires: `session_validation_failure_rate > 50%`.

**09:54 UTC** — On-call pages. Engineer identifies the deploy as the cause.

**10:01 UTC** — Rollback deploy of previous Worker code (`SessionManager` class). Old
`SessionManager` DO namespace is live again. Users who had not yet received a new session
token can recover their sessions.

**10:03 UTC** — Users who received a new (empty) `UserSession` object in the 9-minute window
are still broken: their client-side session cookie points to a `UserSession` ID that now
resolves to an empty object in a class that no longer exists.

**10:21 UTC** — Decision: force-expire all sessions issued between 09:52 and 10:03 and require
re-authentication. Upload state for those users is lost.

## Root Cause Analysis

The `wrangler.toml` rename was the direct cause. Prior to the incident:

```toml
# wrangler.toml — before
[[durable_objects.bindings]]
name        = "USER_SESSIONS"
class_name  = "SessionManager"

[migrations]
tag = "v1"
new_classes = ["SessionManager"]
```

After the PR merged:

```toml
# wrangler.toml — after (incorrect — data loss)
[[durable_objects.bindings]]
name        = "USER_SESSIONS"
class_name  = "UserSession"

[migrations]
tag         = "v2"
new_classes = ["UserSession"]
```

The critical mistake was using `new_classes` instead of `renamed_classes`. The `renamed_classes`
migration type explicitly tells Cloudflare to transfer all existing object IDs and storage from
the old class namespace to the new class namespace:

```toml
# wrangler.toml — correct migration for a rename
[[durable_objects.bindings]]
name        = "USER_SESSIONS"
class_name  = "UserSession"

[[migrations]]
tag             = "v2"
renamed_classes = [{ from = "SessionManager", to = "UserSession" }]
```

By declaring `new_classes = ["UserSession"]` and omitting `renamed_classes`, the migration
told Cloudflare to create a brand-new empty namespace for `UserSession`. No data transfer
occurred. The `SessionManager` namespace was orphaned.

## Impact Analysis

- 9-minute window of 100 % session invalidation for all active users (~4 200 concurrent sessions).
- ~11 minutes of partial recovery confusion while rollback propagated.
- Users active during 09:52–10:03 UTC lost upload progress and collaborative editing state.
- Estimated 220 affected user-sessions with non-recoverable state.
- Post-incident user trust survey showed a 12-point NPS drop in the "reliability" category.
- No PII or billing data was lost; session state was transient by design.

## Remediation

### Immediate: correct migration

The correct `wrangler.toml` once data was confirmed orphaned and un-recoverable:

```toml
[[durable_objects.bindings]]
name        = "USER_SESSIONS"
class_name  = "UserSession"

[[migrations]]
tag             = "v2"
renamed_classes = [{ from = "SessionManager", to = "UserSession" }]
```

Because the orphaned window had already passed and objects in `UserSession` had been populated
with fresh empty sessions, a second migration was authored:

```toml
[[migrations]]
tag             = "v3"
deleted_classes = ["SessionManager"]
```

This formally removes the orphaned `SessionManager` namespace and releases its storage quota.

### Session resilience: graceful empty-object handling

Add initialisation logic so an empty DO gracefully re-hydrates from a server-side session
table rather than throwing:

```typescript
export class UserSession extends DurableObject {
  async getSession(): Promise<SessionData | null> {
    let data = await this.ctx.storage.get<SessionData>('session');
    if (!data) {
      // Attempt to restore from D1 sessions table (soft fallback)
      data = await this.env.DB.prepare(
        'SELECT * FROM sessions WHERE do_id = ?'
      ).bind(this.ctx.id.toString()).first<SessionData>();
      if (data) {
        await this.ctx.storage.put('session', data);
      }
    }
    return data ?? null;
  }
}
```

## Prevention

**Migration linter in CI.** Add a pre-deploy script that diffs `wrangler.toml` against the
previous deployed version and errors when a DO class name changes without a `renamed_classes`
entry:

```bash
#!/usr/bin/env bash
# scripts/check-do-renames.sh
set -euo pipefail

PREV=$(wrangler deployments list --json | jq -r '.[0].id')
OLD_CONFIG=$(wrangler deployments view "$PREV" --config)
NEW_CONFIG=$(cat wrangler.toml)

OLD_CLASSES=$(echo "$OLD_CONFIG" | python3 -c "
import sys, tomllib
cfg = tomllib.loads(sys.stdin.read())
print('\n'.join(b['class_name'] for b in cfg.get('durable_objects',{}).get('bindings',[])))
")

NEW_CLASSES=$(python3 -c "
import sys, tomllib
cfg = tomllib.loads(open('wrangler.toml').read())
print('\n'.join(b['class_name'] for b in cfg.get('durable_objects',{}).get('bindings',[])))
")

REMOVED=$(comm -23 <(sort <<< "$OLD_CLASSES") <(sort <<< "$NEW_CLASSES"))
if [ -n "$REMOVED" ]; then
  echo "ERROR: Durable Object class(es) removed or renamed without a renamed_classes migration:"
  echo "$REMOVED"
  echo "Use renamed_classes migration or deleted_classes if intentionally deleting."
  exit 1
fi
```

**Mandatory two-phase rename checklist.** All DO class renames must follow this sequence:

1. Deploy an alias step: add the new class that delegates to the old one for one full release
   cycle.
2. Deploy the `renamed_classes` migration in a separate commit reviewed by a second engineer.
3. Deploy cleanup: `deleted_classes` for the old name after confirming zero traffic.

**PR template gate for `wrangler.toml` changes:**

```markdown
<!-- .github/PULL_REQUEST_TEMPLATE/wrangler-change.md -->
## Durable Objects checklist
- [ ] No Durable Object class names have been removed or changed without a `renamed_classes` migration
- [ ] Any `renamed_classes` migration has been reviewed by a second engineer
- [ ] A rollback plan is documented if the DO migration is irreversible
```

## Anti-patterns

- Treating a DO class rename as a "cosmetic" code change with no data implications.
- Using `new_classes` when the intent is to rename an existing class (not create a fresh one).
- Merging `wrangler.toml` DO binding changes without a paired migration block review.
- Relying on Worker code rollback to undo a DO namespace migration — migrations are not rolled back
  when a Worker script is reverted.
- Storing critical session state exclusively in DO without a secondary persistence fallback.

## Gotchas

- `renamed_classes` in `wrangler.toml` is the ONLY supported mechanism to rename a DO class
  without data loss. There is no manual migration tool or API to move DO storage between namespaces
  after the fact.
- A rollback of a Worker script does NOT roll back a DO migration. Once `new_classes` is deployed,
  the new empty namespace exists and the old namespace is inaccessible from the new code.
- Deleting a DO class with `deleted_classes` is irreversible and immediately destroys all stored
  data. Cloudflare does not provide a recovery path.
- DO IDs derived from `idFromName()` are class-scoped. The same string name under a different class
  produces a different ID and a different storage namespace.
- The Wrangler deploy pipeline does not warn when a previously declared class disappears from
  `wrangler.toml` without a `renamed_classes` or `deleted_classes` migration.

## Verification

After applying the correct `renamed_classes` migration:

```bash
# 1. Deploy with renamed_classes migration
wrangler deploy

# 2. Confirm old sessions are accessible under the new class name
wrangler do-get USER_SESSIONS <DO_ID_FROM_OLD_CLASS>
# Should return stored session data, not an empty object

# 3. Confirm new session creation works
curl -X POST https://example.com/api/session \
  -H "Content-Type: application/json" \
  -d '{"userId": "test-user-001"}'
# Expect 200 with session token

# 4. Confirm error rate returns to baseline
wrangler tail --format=json | jq 'select(.outcome != "ok") | .exceptions'
```

## Related

- `durable-objects-storage-quota-limit-incident.md`
- `durable-object-alarm-silent-failure-payment-reminders.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `never-delete-without-soft-delete-first.md`

## Sources

- Cloudflare Durable Objects migrations documentation: https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- Cloudflare Workers wrangler.toml reference (durable_objects): https://developers.cloudflare.com/workers/wrangler/configuration/#durable-objects
- Cloudflare community thread on renamed_classes: https://community.cloudflare.com/t/durable-objects-renamed-classes/
