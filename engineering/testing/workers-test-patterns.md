# workers-test-patterns

**Issue:** Structuring unit and integration tests for Cloudflare Workers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers run in a non-Node runtime; standard Jest patterns that rely on `process`, `fs`, or Node globals fail, and mocking fetch is awkward.

## Pattern / Solution
Use `@cloudflare/vitest-pool-workers` which runs tests inside a real workerd isolate:

```ts
// vitest.config.ts
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";
export default defineWorkersConfig({
  test: { poolOptions: { workers: { wrangler: { configPath: "./wrangler.toml" } } } },
});
```

For unit logic extracted from handlers, plain Vitest suffices. For handler integration, use `fetchMock` from `cloudflare:test`:

```ts
import { fetchMock } from "cloudflare:test";
fetchMock.activate();
fetchMock.disableNetConnect();
fetchMock.get("https://api.example.com").reply(200, { ok: true });
```

## Gotchas
- `SELF.fetch()` hits the real worker; external `fetch` is intercepted by `fetchMock`.
- Durable Objects require separate test setup beyond KV/R2.
- Running in workerd means `setTimeout` precision is limited.

## Related
- kv-testing-miniflare
- d1-testing-local
- test-doubles-cloudflare-workers
