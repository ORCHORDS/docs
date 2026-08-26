# Durable Objects Class Rename Migration State Loss Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

On 2026-05-19, a routine refactor that renamed the `PresenceTracker` Durable Object class to `SessionPresence` caused all active user presence data to vanish for approximately 22 minutes following deployment. 8,100 active sessions appeared offline. Real-time collaboration features (cursor sharing, live co-editing) stopped working. The deploy was rolled back but state was not automatically restored — DO storage is tied to the class identity in the namespace binding, not the class name in TypeScript.

## Context

example project engineers renamed the class during a codebase cleanup sprint. The `wrangler.toml` `[[durable_objects]]` binding was updated to reference `SessionPresence`. What was not understood: existing Durable Object instances are keyed by `(namespace binding name, ID)`. Renaming the TypeScript class while keeping the same binding name is safe. But engineers also renamed the binding itself from `PRESENCE_TRACKER` to `SESSION_PRESENCE`, which broke all `env.PRESENCE_TRACKER.idFromName()` lookups and orphaned all existing storage.

---

## Section 1: What Actually Changed and Why It Broke

```toml
# wrangler.toml BEFORE — working configuration
[[durable_objects.bindings]]
name       = "PRESENCE_TRACKER"
class_name = "PresenceTracker"

# wrangler.toml AFTER — broke production
[[durable_objects.bindings]]
name       = "SESSION_PRESENCE"          # <-- renamed binding breaks ID resolution
class_name = "SessionPresence"           # <-- safe to rename
```

The TypeScript class name is only used at script load time to find the export. The **binding name** is the durable namespace identifier — changing it creates a brand-new namespace with empty storage.

---

## Section 2: The Safe Rename — Class Only, Binding Intact

```toml
# wrangler.toml CORRECT — rename class, preserve binding name
[[durable_objects.bindings]]
name       = "PRESENCE_TRACKER"          # unchanged — preserves namespace + storage
class_name = "SessionPresence"           # renamed — safe, it's just a code pointer
```

```typescript
// Worker — binding name in env must match wrangler.toml `name`
const id = env.PRESENCE_TRACKER.idFromName(userId);  // still works
const stub = env.PRESENCE_TRACKER.get(id);
```

If the binding name must change for API clarity, use a two-phase migration (see Section 4).

---

## Section 3: Detecting Orphaned Namespaces Before They Become Incidents

Add a startup health check that verifies the DO namespace is reachable and returns non-empty state for a known sentinel ID.

```typescript
// health-check.ts — called by the Worker's scheduled trigger hourly
async function doNamespaceHealthCheck(env: Env): Promise<void> {
  const SENTINEL_ID = 'healthcheck-sentinel';
  const id = env.PRESENCE_TRACKER.idFromName(SENTINEL_ID);
  const stub = env.PRESENCE_TRACKER.get(id);

  const resp = await stub.fetch('https://do/ping');
  if (!resp.ok) {
    throw new Error(`DO namespace health check failed: ${resp.status}`);
  }

  // Confirm the sentinel has been seen before (validates storage continuity)
  const pingResp: { seenAt: number | null } = await resp.json();
  if (pingResp.seenAt === null) {
    console.warn('[DO health] Sentinel has no stored state — namespace may be new or reset');
  }
}
```

---

## Section 4: Two-Phase Binding Rename Migration

When the binding name itself must change, migrate in two stages across two separate deploys with an overlap window.

```typescript
// Phase 1 deploy — add NEW binding, keep OLD binding live
// wrangler.toml
// [[durable_objects.bindings]]
// name       = "PRESENCE_TRACKER"   # old, still active
// class_name = "SessionPresence"
//
// [[durable_objects.bindings]]
// name       = "SESSION_PRESENCE"   # new, empty — warming up
// class_name = "SessionPresence"

// Worker — dual-write during migration window
async function getPresenceStub(userId: string, env: Env): Promise<DurableObjectStub> {
  const legacyId = env.PRESENCE_TRACKER.idFromName(userId);
  const legacyStub = env.PRESENCE_TRACKER.get(legacyId);

  const newId = env.SESSION_PRESENCE.idFromName(userId);
  const newStub = env.SESSION_PRESENCE.get(newId);

  // Migrate state on first access
  const migrated = await newStub.fetch('https://do/has-migrated');
  if (!(await migrated.json<{ done: boolean }>()).done) {
    const legacy = await legacyStub.fetch('https://do/export');
    const state = await legacy.json();
    await newStub.fetch('https://do/import', {
      method: 'POST',
      body: JSON.stringify(state),
    });
  }

  return newStub;
}
```

Phase 2 deploy (after full migration): remove old binding from `wrangler.toml` and worker code.

---

## Section 5: Pre-Deploy Checklist for DO Changes

```typescript
// scripts/validate-do-bindings.ts — run in CI before any wrangler deploy
import { execSync } from 'child_process';

interface Binding { name: string; class_name: string; }

const previousBindings: Binding[] = JSON.parse(
  execSync('git show HEAD~1:wrangler.toml | npx toml-json').toString()
).durable_objects?.bindings ?? [];

const currentBindings: Binding[] = JSON.parse(
  execSync('cat wrangler.toml | npx toml-json').toString()
).durable_objects?.bindings ?? [];

const prevNames = new Set(previousBindings.map(b => b.name));
const currNames = new Set(currentBindings.map(b => b.name));

const removed = [...prevNames].filter(n => !currNames.has(n));
if (removed.length > 0) {
  console.error(
    `ERROR: DO binding(s) removed: ${removed.join(', ')}\n` +
    `Removing a binding orphans all storage. Use two-phase migration.`
  );
  process.exit(1);
}
```

This script is added to the CI pipeline as a mandatory pre-deploy gate.

---

## Anti-patterns

- Renaming a Durable Object binding in `wrangler.toml` as if it were just a variable rename — it creates a new empty namespace.
- Treating the TypeScript class name and the `wrangler.toml` binding `name` as the same thing — they are independent identifiers.
- Performing DO namespace migrations in a single atomic deploy instead of a phased dual-write approach.
- Assuming rollback restores DO state — rollback only restores the Worker script; DO storage is independent and persistent.

## Gotchas

- `idFromName()` is deterministic within a namespace binding, but the same string produces a different ID in a different binding.
- DO storage is not included in `wrangler.toml` diffs or deploy previews — storage changes are invisible until runtime.
- Wrangler does not warn when a binding name is removed; the old namespace becomes orphaned silently.
- `env.DO_NAMESPACE.jurisdiction('eu')` creates yet another distinct namespace — do not mix jurisdictions during migration.

## Verification

1. Run `scripts/validate-do-bindings.ts` in CI on every PR that touches `wrangler.toml`.
2. After Phase 1 deploy, confirm new binding returns expected migrated state via the health-check sentinel.
3. Before Phase 2 deploy, verify `SESSION_PRESENCE` namespace has non-zero key count via the Cloudflare dashboard > Durable Objects > Storage.
4. Keep the old binding live for at least one full on-call rotation (7 days) before Phase 2 removal.

## Related

- `durable-objects-namespace-rename-data-loss-incident.md`
- `durable-objects-storage-quota-limit-incident.md`
- `durable-objects-websocket-hibernation-migration-adr.md`
- `always-test-rollback-before-deploying.md`
- `migrations-must-be-backward-compatible.md`

## Sources

- Cloudflare Durable Objects — Namespace bindings: https://developers.cloudflare.com/durable-objects/reference/bindings/
- Cloudflare Durable Objects — Migration guide: https://developers.cloudflare.com/durable-objects/reference/durable-objects-migrations/
- example project incident ticket INC-2026-0519-DO-RENAME
