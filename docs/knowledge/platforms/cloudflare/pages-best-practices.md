# pages-best-practices

**Issue:** Cloudflare Pages — static sites, Functions, previews
**Date:** 2026-08-09
**Status:** documented

## Symptom
You deploy a static site. You have a contact form.
The form needs a server. You add a server. The deploy
breaks. You wish you had a single platform.

## Root cause
**Static + dynamic need a single deploy.** Use Pages
with Functions.

**Source:** CF Pages docs:
https://developers.cloudflare.com/pages/

## The "Pages" concept

Cloudflare Pages:
- **Static site:** HTML / CSS / JS
- **Functions:** Server-side code (Workers)
- **Git integration:** Auto-deploy on push
- **Preview deploys:** Per PR
- **Custom domain:** Easy setup
- **Free SSL:** Auto

The site is static + dynamic.

## The "build" pattern

For a build:
```toml
# wrangler.toml / pages config
[build]
command = "npm run build"
output = "dist"
```

The build is configured.

## The "Functions" pattern

For Functions, the directory:
```
/functions
  /api
    /users.ts
    /posts.ts
  /auth
    /login.ts
```

Each file is a function.

## The "Function" pattern

For a Function:
```ts
// functions/api/users.ts
export const onRequestGet: PagesFunction<Env> = async (context) => {
  const users = await context.env.DB!.prepare(`SELECT * FROM users`).all();
  return Response.json(users.results);
};
```

The function is type-safe.

## The "Pages + D1" pattern

For D1 binding:
```toml
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "..."
```

D1 is bound.

## The "Pages + R2" pattern

For R2 binding:
```toml
[[r2_buckets]]
binding = "R2"
bucket_name = "my-bucket"
```

R2 is bound.

## The "Pages + KV" pattern

For KV:
```toml
[[kv_namespaces]]
binding = "KV"
id = "..."
```

KV is bound.

## The "preview deploys" pattern

For preview deploys (per PR):
- **Auto:** Per PR
- **URL:** `<branch>.<project>.pages.dev`
- **Comment on PR:** With the URL

The preview is per PR.

## The "direct upload" pattern

For direct upload:
```bash
npx wrangler pages deploy ./dist
```

The site is deployed.

## The "Pages limits" pattern

For limits:
- **File count:** 20,000
- **File size:** 25 MB per file
- **Total size:** Unlimited (effectively)
- **Functions CPU:** 30s (paid)
- **Functions memory:** 128 MB

The limits are checked.

## The "Pages vs Workers" choice

| Use case | Use |
|---|---|
| **Static site + light API** | Pages |
| **Full backend** | Workers |
| **Auto-deploy from Git** | Pages |
| **Complex routing** | Workers |
| **Custom domain** | Both |

For most apps, **Pages** is the right answer.

## The "Pages observability" pattern

For observability:
- **Build logs:** In dashboard
- **Function logs:** Real-time tail
- **Analytics:** Per route
- **Web Vitals:** Real user metrics

The metrics are in the dashboard.

## The "Pages + Framework" pattern

For frameworks:
- **Next.js:** Static export
- **Astro:** Native
- **SvelteKit:** Adapter
- **Vue / Nuxt:** Adapter
- **Remix:** Adapter

For most, the adapter is built-in.

## The "Pages anti-pattern" anti-patterns

### 1. Heavy server in Functions
- **Issue:** CPU timeout
- **Fix:** Queue + Worker

### 2. No preview
- **Issue:** Bugs in prod
- **Fix:** Preview deploys

### 3. No custom domain
- **Issue:** Looks unprofessional
- **Fix:** Custom domain

### 4. No build cache
- **Issue:** Slow builds
- **Fix:** Cache node_modules

## Verification
- **Test:** Build works
- **Test:** Functions work
- **Test:** Preview deploys work
- **Live:** Site is monitored
- **Audit:** Quarterly review

## Gotchas
- **The "heavy server in Functions" anti-pattern.**
  Use a queue.
- **The "no preview" anti-pattern.** Use previews.

## Related
- `cloudflare/workers-best-practices.md`
- `cloudflare/d1-best-practices.md`
- `feature-cookbook-deploy.md`
- `feature-environment-promotion.md`
- CF Pages: https://developers.cloudflare.com/pages/
