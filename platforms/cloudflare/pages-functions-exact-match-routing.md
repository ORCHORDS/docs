# pages-functions-exact-match-routing

**Issue:** `functions/api/foo.ts` does NOT match `/api/foo/bar`
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** documented (Cloudflare behavior, not a bug)

## Symptom
You write `functions/api/foo.ts` with `export const onRequest: PagesFunction`,
expecting it to handle `GET /api/foo/anything`. But a `curl /api/foo/123`
returns 404, even though the file is deployed.

```bash
$ curl -i https://the domain/api/foo/123
HTTP/2 404
```

## Root cause
CF Pages Functions uses **exact-match** routing for non-bracketed
filenames. `functions/api/foo.ts` matches ONLY `/api/foo` (the
trailing slash and any sub-paths do NOT match).

**Source:** Cloudflare Pages Functions routing docs:
https://developers.cloudflare.com/pages/functions/routing/

> "Functions files placed in the `functions/` directory are matched
> to routes based on their file path. A file at `functions/api/hello.ts`
> only matches the exact path `/api/hello`."

## Fix
Three options, in order of preference:

### Option 1: Catch-all with `[[path]].ts`
For dynamic sub-paths:
```ts
// functions/api/foo/[[path]].ts
export const onRequest: PagesFunction = async (context) => {
  const subpath = context.params.path; // ["123"] or ["a", "b"]
  // ... handle /api/foo/<anything>
};
```

The double brackets mean "match zero or more path segments." So
`/api/foo`, `/api/foo/123`, and `/api/foo/a/b/c` all match.

### Option 2: Single param with `[id].ts`
For a known shape (one sub-segment):
```ts
// functions/api/foo/[id].ts
export const onRequest: PagesFunction = async (context) => {
  const id = context.params.id as string;
  // ... handle /api/foo/<single-segment-id>
};
```

This matches `/api/foo/123` but NOT `/api/foo/123/456`. Use when
the resource hierarchy is one level deep.

### Option 3: File-name with literal sub-paths
For a few known paths:
```
functions/api/foo/list.ts      // matches /api/foo/list
functions/api/foo/create.ts    // matches /api/foo/create
```

Verbose but readable. Use when there are < 5 endpoints and they're
all distinct verbs.

## Verification
- **Test:** `test/routing.test.ts` — exercises each pattern
- **Live:** `wrangler pages dev` locally; `curl -v` to confirm routing

## Gotchas
- **The `_` prefix excludes files from routing.** `functions/api/_utils.ts`
  is a module, not a route. Use this for shared helpers.
- **Build output is `dist/_worker.js`.** If you see functions in the
  source but not in the bundle, check for `_` prefix.
- **`_middleware.ts` is special.** It runs on EVERY request in its
  directory subtree. Use sparingly.
- **Static assets win over functions.** If you have
  `public/api/foo.json` AND `functions/api/foo.ts`, the static
  asset is served, not the function. Rename to avoid collision.
- **Match order is alphabetic within a directory.** `[[path]].ts`
  always wins last; `[id].ts` is alphabetical; `foo.ts` is exact.

## Related
- Cloudflare Pages Functions routing: https://developers.cloudflare.com/pages/functions/routing/
- Same pattern in a sibling repo: `functions/api/mc/[[path]].ts` catch-all
  handles 80+ API endpoints
