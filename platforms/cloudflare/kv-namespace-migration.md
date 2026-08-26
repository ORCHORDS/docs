# kv-namespace-migration

**Issue:** Migrating data between KV namespaces or environments without downtime
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When renaming a KV namespace, moving from preview to production, or consolidating namespaces, you need to copy keys without service interruption. KV has no native copy API — migration requires reading and re-writing keys.

## Pattern / Solution

**List and copy via Wrangler CLI:**
```bash
# List all keys in source namespace
wrangler kv key list --namespace-id $SRC_NS_ID --env production > keys.json

# Copy each key (bash loop)
jq -r '.[].name' keys.json | while read key; do
  VALUE=$(wrangler kv key get "$key" --namespace-id $SRC_NS_ID)
  wrangler kv key put "$key" "$VALUE" --namespace-id $DST_NS_ID
done
```

**Programmatic migration Worker:**
```typescript
// Run as a one-off scheduled Worker
export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(migrateKV(env));
  },
};

async function migrateKV(env: Env): Promise<void> {
  let cursor: string | undefined;
  let total = 0;

  do {
    const list = await env.SOURCE_KV.list({ cursor, limit: 1000 });

    // Fetch all values in parallel (batched to avoid subrequest limits)
    const entries = await Promise.all(
      list.keys.map(async ({ name, expiration, metadata }) => {
        const value = await env.SOURCE_KV.get(name, { type: 'arrayBuffer' });
        return { name, value, expiration, metadata };
      })
    );

    // Write to destination
    await Promise.all(
      entries
        .filter(e => e.value !== null)
        .map(({ name, value, expiration, metadata }) =>
          env.DEST_KV.put(name, value!, {
            expiration,          // preserve TTL
            metadata,            // preserve metadata
          })
        )
    );

    total += entries.length;
    console.log(`Migrated ${total} keys...`);
    cursor = list.list_complete ? undefined : list.cursor;
  } while (cursor);

  console.log(`Migration complete: ${total} keys`);
}
```

**Zero-downtime strategy:**
1. Deploy code that writes to **both** old and new namespace simultaneously.
2. Run the migration Worker to backfill historical keys.
3. Verify new namespace has all keys.
4. Switch reads to new namespace.
5. Remove dual-write code and old namespace binding.

## Gotchas
- KV `list()` returns keys in **lexicographic order** — pagination with `cursor` is required for >1000 keys.
- `list()` does not return values — you must `get()` each key separately (counts as a read operation).
- KV reads are **eventually consistent** — allow up to 60 seconds after writes before trusting all edge nodes are updated.
- Expiration timestamps (`expiration`) are **Unix epoch seconds** — verify they haven't already expired before copying.
- Metadata is limited to 1024 bytes; oversized metadata silently fails on `put()`.
- Large migrations may exceed Worker CPU time — use `scheduled` events or external scripts.

## Related
- `kv-best-practices.md`
- `kv-eventually-consistent.md`
- `workers-scheduled-events.md`
