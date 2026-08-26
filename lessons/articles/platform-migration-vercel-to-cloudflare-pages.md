# Platform Migration Lessons: Moving from Vercel to Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Your Vercel bill has crossed the point where it is no longer defensible at startup
scale. Or you are already on Cloudflare Workers for your API and the two-platform
split is creating operational friction: different secret stores, different deploy
pipelines, different dashboards, different edge network semantics. Or you simply want
everything in one control plane so that a single `wrangler deploy` ships both the
front-end Pages project and the backing Worker.

Whatever the trigger, migrating a Next.js / SvelteKit / Astro / Remix front-end from
Vercel to Cloudflare Pages is not "just a DNS cut-over." This article documents the
failure modes that bite teams who underestimate the divergence.

---

## Context

Vercel and Cloudflare Pages both call themselves "edge hosting for modern frameworks."
The marketing similarity obscures meaningful runtime differences:

| Concern | Vercel | Cloudflare Pages |
|---|---|---|
| Runtime | Node.js Lambda + Edge Runtime (V8) | Workers runtime (V8, no Node.js) |
| Build output | Vercel output spec | Pages Functions or `_worker.js` |
| Middleware | `middleware.ts` — Next.js only | Pages Functions or a Worker route |
| Env secrets | Vercel project settings | `wrangler secret` or Pages dashboard |
| Preview envs | Per-PR, auto | Per-branch, requires branch alias config |
| Monorepo | `vercel.json` root + workspace pointer | `wrangler.toml` `pages_build_output_dir` |
| Analytics | Vercel Analytics (JS SDK) | Cloudflare Web Analytics (beacon or Worker) |
| ISR / On-demand revalidation | First-class | Not available — you need a Cache API strategy |

The runtime gap is the most dangerous. Code that imports `node:crypto`, uses
`fs.readFileSync` at module load time, or relies on `process.env` set outside
`wrangler.toml` will silently break or fail to build.

---

## Section 1 — Audit Before You Migrate

Run the audit as a checklist, not as a gut-feel pass.

**1.1 Framework adapter**
Cloudflare provides official adapters for SvelteKit, Astro, and Remix.
Next.js support is provided by the community `@cloudflare/next-on-pages` package,
which imposes constraints (no `getServerSideProps` with Node APIs, no custom server).
Pin the adapter version and read its changelog. Breakage usually comes from upgrading
the adapter without upgrading the framework, or the reverse.

**1.2 Node.js API surface**
Search your codebase for any import of a Node.js built-in:
```
grep -rE "require\('(fs|path|crypto|os|child_process|stream)'\)|from ['\"]node:" src/
```
Every hit is a migration task. Common mitigations:
- `node:crypto` → `crypto.subtle` (Web Crypto API, available in Workers)
- `node:fs` → only possible at build time, not at request time
- `node:stream` → `ReadableStream` (WHATWG)

**1.3 Environment variables**
Vercel supports env vars injected at build time AND at runtime. Workers/Pages
distinguishes between build-time vars (set in `wrangler.toml` or Pages project
settings → `[vars]`) and runtime secrets (`wrangler secret put`). If your app reads
an env var that is only available at request time, it must come through the Workers
binding system, not `process.env`.

**1.4 Middleware / edge logic**
Any Vercel middleware (`middleware.ts`) must be rewritten as a Pages Function
(`functions/_middleware.ts`) or moved into a Worker route. The semantics differ:
Vercel middleware runs before the cache; a Pages Function `_middleware.ts` runs on
every request to the Pages project. Caching behavior changes accordingly.

**1.5 Preview environment expectations**
Vercel auto-deploys every PR to a unique URL. Cloudflare Pages deploys every push to
a branch. If your team relies on PR-scoped URLs for QA sign-off, configure branch
aliases in your Pages project and document that the preview URL is branch-scoped, not
commit-scoped.

---

## Section 2 — Migration Sequencing

Do not do a big-bang cut-over. Use the strangler fig pattern even for front-end
migrations.

**Phase 1 — Parallel deploy**
Keep Vercel live. Add a second deploy target: push the same repo to Cloudflare Pages.
Your DNS still points at Vercel. Team validates the Pages build on the `pages.dev`
subdomain.

**Phase 2 — Adapter and runtime fixes**
Fix every audit finding. Run `wrangler pages dev` locally. Treat any error in the
Cloudflare runtime as a blocker, not a "we'll fix after launch" item.

**Phase 3 — Traffic split (optional)**
If your domain is already on Cloudflare, use a Worker to split traffic:
```js
// traffic-split worker
const CLOUDFLARE_PAGES_HOST = 'your-project.pages.dev';
const VERCEL_HOST = 'your-project.vercel.app';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const target = Math.random() < 0.1 ? CLOUDFLARE_PAGES_HOST : VERCEL_HOST;
    url.hostname = target;
    return fetch(url.toString(), request);
  }
};
```
Start at 5 %, watch error rates, increment.

**Phase 4 — DNS cut-over**
Lower your DNS TTL to 60 seconds 24 hours before the cut. Point the custom domain to
Cloudflare Pages. Keep Vercel deployed for 48 hours as a rollback target.

**Phase 5 — Decommission**
Remove the Vercel project only after two full release cycles with no production
incidents attributable to the migration.

---

## Section 3 — Secrets and Bindings After Migration

The biggest operational friction post-migration is secrets management. Vercel's UI is
a single screen. Cloudflare has three mechanisms and teams mix them up:

- **`wrangler.toml` `[vars]`** — plain text, committed to the repo, visible to all
  team members. Only for non-sensitive config (e.g., `ENVIRONMENT=production`).
- **`wrangler secret put`** — encrypted at rest, injected at runtime, not visible in
  the dashboard. Use for API keys, database passwords, signing secrets.
- **Pages dashboard → Settings → Environment variables** — equivalent to
  `wrangler secret put` for Pages projects. Still encrypted; use for variables that
  change per environment (preview vs production).

Rotation discipline does not change: rotate on engineer offboarding, rotate if a
secret appears in a log, rotate on a vendor breach notification.

---

## Section 4 — Observability Gaps to Close

Vercel gives you function logs in the dashboard out of the box. Cloudflare Pages
gives you Workers logs via `wrangler tail` and Cloudflare's Logpush to R2 or a SIEM.

Close these gaps before DNS cut-over:

1. **Real-user monitoring**: Add Cloudflare Web Analytics (one script tag or a Worker
   beacon). Do not rely on Vercel Analytics SDK — it will stop receiving data.
2. **Error tracking**: Configure your error tracking SDK (Sentry, etc.) with the
   Cloudflare Worker source-map upload step in your CI pipeline. Source maps for
   Pages Functions live in `.vercel/output` on Vercel but in the Cloudflare build
   artifact on Pages.
3. **Structured logs**: Pages Functions can call `console.log()` and these appear in
   `wrangler tail`. For higher volume, ship logs to Workers Analytics Engine or
   Logpush.
4. **Synthetic monitoring**: Update any synthetic checks (Checkly, Playwright-based
   checks) that ping Vercel URLs. Point them at the new domain immediately post-cut.

---

## Anti-patterns

- **Migrating without running `wrangler pages dev` locally first.** The first time
  you discover a Node.js API incompatibility should not be in a production deploy.
- **Assuming ISR (Incremental Static Regeneration) works the same way.** It does not.
  You need a Cache API strategy or Cloudflare's Cache-Control headers approach.
  Teams that rely heavily on ISR should plan additional re-architecture time.
- **Keeping secrets in both platforms.** When you have two deploy targets active
  simultaneously, secrets drift. Maintain a single source of truth (a password
  manager or a secrets manager like 1Password Secrets Automation) and push to both
  platforms from there.
- **Copying Vercel preview URL patterns into PR templates and Slack bots.**
  These will break or point at the wrong environment after migration.
- **Forgetting to migrate cron triggers.** Vercel Cron is `vercel.json` → `crons`.
  Cloudflare Cron is a Scheduled Worker (`[triggers]` in `wrangler.toml`). They are
  different runtimes with different timeout limits.

---

## Gotchas

- **`@cloudflare/next-on-pages` does not support all Next.js features.** Check the
  compatibility matrix before committing to the migration timeline. App Router is
  better supported than Pages Router for some features, and vice versa for others.
- **Workers have a 128 MB memory limit per isolate by default.** Large server
  components that hold significant in-memory state may OOM in ways they did not on
  Vercel Lambda (which has a configurable 1 GB default).
- **Cold start semantics differ.** Workers use isolate reuse, not Lambda cold starts.
  The performance profile is different: Workers have lower median latency but their
  isolate lifecycle is opaque. Do not assume Vercel cold-start optimisations (e.g.,
  connection pooling tricks) apply.
- **Cloudflare Pages build times count toward your plan limits.** For monorepos with
  many packages, configure `wrangler.toml` `pages_build_output_dir` carefully and
  skip unnecessary workspace package builds in CI.
- **Custom headers (`_headers` file) are processed differently from Vercel's
  `headers` in `vercel.json`.** Re-test all security headers (CSP, HSTS, Permissions-
  Policy) after migration using `curl -I` or a header checker.

---

## Verification

Before DNS cut-over, run this checklist against the `pages.dev` URL:

- [ ] All routes return 200 (or expected redirects)
- [ ] Auth flows complete end-to-end (cookies, sessions, OAuth redirects)
- [ ] API routes / Pages Functions return correct responses
- [ ] Environment-specific config is correct (staging vs production vars)
- [ ] Error tracking receives a test error event
- [ ] Web Analytics beacon fires (check Cloudflare dashboard)
- [ ] Security headers match the pre-migration baseline
- [ ] Cron triggers have fired at least once in staging
- [ ] Rollback plan is documented and tested (Vercel still live)
- [ ] DNS TTL is reduced 24 h before cut-over

---

## Related

- `developer-experience-dx-cloudflare-workers.md`
- `big-bang-rewrite-fails-strangler-fig-wins.md`
- `never-store-secrets-in-env-files.md`
- `monitor-before-and-after-deploy.md`
- `dns-ttl-incidents-during-migration.md`

---

## Sources

- Cloudflare Pages documentation: https://developers.cloudflare.com/pages/
- `@cloudflare/next-on-pages` GitHub: https://github.com/cloudflare/next-on-pages
- Cloudflare Workers runtime APIs: https://developers.cloudflare.com/workers/runtime-apis/
- Strangler Fig pattern (Martin Fowler): https://martinfowler.com/bliki/StranglerFigApplication.html
