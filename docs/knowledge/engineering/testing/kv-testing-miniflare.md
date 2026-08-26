# kv-testing-miniflare

**Issue:** Testing Cloudflare KV bindings locally without deploying
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
KV namespace calls fail or require real Cloudflare credentials during local test runs, slowing the feedback loop and making CI brittle.

## Pattern / Solution
Use Miniflare (or Wrangler's built-in `--local` mode) to emulate KV in process:

```ts
import { Miniflare } from "miniflare";

let mf: Miniflare;

beforeAll(async () => {
  mf = new Miniflare({
    kvNamespaces: ["MY_KV"],
    modules: true,
    scriptPath: "./dist/worker.js",
  });
});

afterAll(() => mf.dispose());

test("stores and retrieves a value", async () => {
  const kv = await mf.getKVNamespace("MY_KV");
  await kv.put("key", "value");
  expect(await kv.get("key")).toBe("value");
});
```

With Vitest + `@cloudflare/vitest-pool-workers`, declare KV in `wrangler.toml` and access via `env.MY_KV` directly in test files.

## Gotchas
- Miniflare v3 API differs from v2 — check version before copying snippets.
- TTL behaviour in Miniflare is approximate; do not rely on sub-second expiry in tests.
- `list()` pagination in local KV is not always consistent with production.

## Related
- d1-testing-local
- test-doubles-cloudflare-workers
- workers-test-patterns
