# big-three-gotchas

**Issue:** Top 3 CF Pages Functions + D1 + Workers pitfalls that bite every green project
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (workarounds in place)

## The top 3 landmines (apply to ALL CF projects)

### 1. D1 `db.batch()` broken in Pages Functions bundler

The CF Pages Functions bundler (esbuild + wrangler 4.x) walks the
AST and silently strips the `sql` field from any
`D1PreparedStatement` argument to `db.batch()`. The bundler
mistakes the SQL string for a "dead" string literal.

```ts
// ❌ BROKEN — bundler strips `sql`, batch() runs empty
await env.DB.batch([
  env.DB.prepare('CREATE TABLE foo (id INTEGER)'),
  env.DB.prepare('INSERT INTO foo VALUES (1)'),
]);

// ✅ FIX — use db.exec() for DDL, sequential .run() for DML
await env.DB.exec('CREATE TABLE foo (id INTEGER);');
await env.DB.prepare('INSERT INTO foo VALUES (?)').bind(1).run();
```

See: `d1-batch-bundler-bug.md` for full details.

### 2. `functions/api/foo.ts` only matches `/api/foo` EXACTLY

CF Pages Functions uses exact-match routing for non-bracketed
filenames. `functions/api/foo.ts` matches ONLY `/api/foo`, not
`/api/foo/123` or `/api/foo/sub/path`.

```ts
// ❌ BROKEN — only handles /api/foo (exact)
export const onRequest: PagesFunction = ...;

// ✅ FIX — use [[path]].ts catch-all for dynamic sub-paths
// functions/api/foo/[[path]].ts
export const onRequest: PagesFunction = async (context) => {
  const subpath = context.params.path; // ["123"] or ["a", "b"]
};
```

See: `pages-functions-exact-match-routing.md` for full details.

### 3. PBKDF2 max 100k iterations in `crypto.subtle.deriveBits`

Web Crypto's `subtle.deriveBits()` for PBKDF2 caps iterations at
**100,000** in some implementations (workerd does). Above the cap,
the call throws `DataError: Cannot derive bits` — same error as a
bad salt. Cap at 100k + use a server-side pepper.

```ts
// ❌ BROKEN — exceeds workerd's PBKDF2 cap
const key = await crypto.subtle.deriveBits(
  { name: 'PBKDF2', salt, iterations: 1_000_000, hash: 'SHA-256' },
  baseKey, 256,
);

// ✅ FIX — cap at 100k + pepper
const ITERATIONS = 100_000;
const key = await crypto.subtle.deriveBits(
  { name: 'PBKDF2', salt: saltWithPepper, iterations: ITERATIONS, hash: 'SHA-256' },
  baseKey, 256,
);
```

See: `pbkdf2-max-100k-iterations.md` for full details.

## Honorable mentions (also bite)

- **`_`-prefixed files NOT routed.** `functions/api/_utils.ts` is
  a module, not a route. Use this for shared helpers.
- **`IF NOT EXISTS` no-op if prior attempt left different schema.**
  A failed migration leaves the DB in a partial state; re-running
  `CREATE TABLE IF NOT EXISTS` does NOT recover.
- **SPA `_redirects` intercepts `/api/*` POSTs.** If you have a
  Cloudflare Pages SPA with `_redirects` for client-side routing,
  the `/* → /index.html 200` rule catches `/api/*` too. Add an
  explicit rule: `/api/* /api/:splat 200` to short-circuit.
- **import resolution from file dir.** Workers don't auto-resolve
  relative imports to `node_modules`. Use explicit paths or
  `wrangler.toml` `[build]` config.
- **`enc.encode(uint8array)` returns CSV "0,0,0,..."** — silently
  breaks PBKDF2/subtle.deriveBits. Use the Uint8Array directly.
- **MERKLE chain canonical JSON** needs sorted keys + recursive
  normalization, not just `JSON.stringify`.

## How to remember all this

1. **Read this file** before writing any CF Pages Functions code.
2. **Run the 3 smoke tests** in your CI: (a) a batch INSERT, (b) a
   multi-segment /api/* route, (c) a 100k+ iteration PBKDF2.
3. **Open an issue** when you find a new gotcha. Add to this list.
4. **The KB is your friend.** Search `documentation/categories/cloudflare/`
   before debugging a CF-specific issue.

## Verification
- **Test:** `test/cf-gotchas.test.ts` — 3 smoke tests, all pass
- **CI:** The orchard project + the platform both have these as
  pre-deploy checks
- **Live:** No 5xx on any of the 3 patterns in production

## Related
- All `documentation/categories/cloudflare/*.md` entries
- The "cloudflare-pages-functions-gotchas" memory topic (preserved
  across sessions)
