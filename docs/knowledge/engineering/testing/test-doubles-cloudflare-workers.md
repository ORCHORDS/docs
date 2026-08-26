# test-doubles-cloudflare-workers

**Issue:** Creating test doubles for Cloudflare Workers runtime APIs (KV, D1, R2, Queue)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Cloudflare Workers bindings (KV, D1, Queues) are not available in Node.js test environments. Tests need in-memory implementations.

## Pattern / Solution
```ts
// In-memory KV stub
class MockKVNamespace implements KVNamespace {
  private store = new Map<string, string>();

  async get(key: string) { return this.store.get(key) ?? null; }
  async put(key: string, value: string) { this.store.set(key, value); }
  async delete(key: string) { this.store.delete(key); }
  async list() { return { keys: [...this.store.keys()].map(name => ({ name })), list_complete: true, cursor: "" }; }
}

// Usage in handler test
it("returns cached value from KV", async () => {
  const kv = new MockKVNamespace();
  await kv.put("user:1", JSON.stringify({ name: "Alice" }));

  const env = { KV: kv } as unknown as Env;
  const req = new Request("https://example.com/users/1");
  const res = await handleRequest(req, env);

  expect(res.status).toBe(200);
  const body = await res.json();
  expect(body.name).toBe("Alice");
});
```

For realistic testing, use Miniflare:
```ts
import { Miniflare } from "miniflare";
const mf = new Miniflare({ kvNamespaces: ["KV"], script: "..." });
```

## Gotchas
- Mock only the methods your code actually calls
- Miniflare is more accurate but slower than in-memory stubs
- Use `wrangler dev` for true integration testing

## Related
- `d1-testing-local.md`
- `kv-testing-miniflare.md`
- `workers-test-patterns.md`
