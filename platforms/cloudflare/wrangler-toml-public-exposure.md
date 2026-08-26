# wrangler-toml-public-exposure

**Issue:** On example project (Cloudflare Pages), `wrangler.toml` was present in the build output directory, and Pages serves every file in the build output at the deployed URL — so `https://<app>.pages.dev/wrangler.toml` returned the full config file publicly. Binding names, KV namespace IDs, and above all any `[vars]` value would be readable by anyone. The fix was a hard rule: nothing sensitive ever goes in wrangler.toml — secrets live only in `wrangler secret put` / dashboard encrypted variables, and bindings whose configuration itself is sensitive (the GUEST_SIGNAL KV binding, R2_UPLOAD_SECRET) were configured dashboard-only so they need no config-file entry at all.

**Date:** 2026-08-15
**Repo:** example-org/example-repo (fork example-org/example-repo)
**Author:** ORCHORDS
**Status:** published

## Why the file is public

1. **Pages serves the entire build output directory.** Pages has no notion of "hidden" files: whatever the build emits in the output directory is a publicly fetchable static asset. `wrangler.toml` sitting in the repo root or copied into the output becomes `GET /wrangler.toml` on the production domain. The same is true of Workers Static Assets, where [Wrangler uploads everything in the assets directory](https://developers.cloudflare.com/workers/static-assets/) verbatim.
2. **Any config file name is affected.** The exposure is not TOML-specific: `wrangler.json`, `wrangler.jsonc`, `.env`, `package.json`, CI files in output — all are served if present in the output directory. Note that JSON (`.json`/`.jsonc`) is now Cloudflare's [recommended config format](https://developers.cloudflare.com/workers/wrangler/configuration/) and TOML is legacy, but the serving behavior is identical.
3. **`[vars]` are plaintext by design.** Cloudflare's [environment variables docs](https://developers.cloudflare.com/workers/configuration/environment-variables/) are explicit: vars in the config file are plaintext build/deploy-time configuration, not secrets — they are visible in the repo, the dashboard, and (in this failure mode) the deployed site. Treating `[vars]` as a place for anything secret is the root mistake.

## What leaks when wrangler.toml is served

1. **Secret values committed as vars.** API keys, webhook secrets, upload tokens pasted into `[vars]` — full compromise, immediately harvestable by crawlers scanning `*.pages.dev` and custom domains for `/wrangler.toml`, `/wrangler.json`, `/.env`.
2. **Binding topology.** KV namespace IDs, D1 database IDs, R2 bucket bindings, queue names, routes, and internal hostnames. Not credentials by themselves, but they hand an attacker a precise map of the infrastructure behind the Worker — useful for targeted phishing, support-engineering attacks ("please rotate KV namespace X"), or probing misconfigured APIs. This is the class of exposure [Assetnote's Cloudflare Pages research](https://www.assetnote.io/resources/research/cloudflare-pages-part-1-the-fellowship-of-the-secret) catalogs in build-configuration leakage.
3. **Build metadata.** Compatibility dates, service bindings, and environment names reveal the deployment shape and staging/production split.

## Correct secret and binding management

1. **Secrets: `wrangler secret put` or dashboard encrypted variables — never the config file.** `wrangler pages secret put NAME` (Pages) / `wrangler secret put NAME` (Workers) stores the value encrypted, masked in the dashboard and logs, and outside the repo entirely. Access in code is identical (`env.NAME`), so there is no code change to make — only deployment-process change.
2. **Dashboard-only bindings when config exposure is unacceptable.** Bindings configured in the Pages dashboard (Settings → Functions → bindings) require no `wrangler.toml` entry. example project used exactly this for the GUEST_SIGNAL KV binding and R2_UPLOAD_SECRET: nothing about them appears in any file that could ship to the output directory. The tradeoff is that dashboard config is not version-controlled — document it in the repo README/deploy runbook so environments are reproducible.
3. **Keep non-secret config in the file.** Bindings that are safe to publish (binding names, D1 `database_id`, KV `id`) can stay in wrangler.toml per the [Pages wrangler configuration docs](https://developers.cloudflare.com/pages/functions/wrangler-configuration/) — the file being fetchable is harmless if it contains only publishable identifiers. Audit it as if it were public, because it is.
4. **Beware the deploy-wipes-vars footgun.** Community reports (e.g., the [wrangler deploy vs dashboard settings complaint](https://www.reddit.com/r/CloudFlare/comments/1m25tkq/wrangler_sucks/)) show config-file vars can interact badly with dashboard-set values on redeploy; keep one source of truth per binding (file for public config, dashboard/secret store for sensitive values) and never duplicate across both.

## Detection and guardrails

1. **Verify by fetching the deployed URL.** `curl -s https://<deployed-host>/wrangler.toml -o /dev/null -w "%{http_code}"` must return 404 on every environment; do the same for `/wrangler.json`, `/wrangler.jsonc`, and `/.env`. This is the only proof that the file is not shipping — build-log inspection is not.
2. **Exclude the config from build output at the source.** Ensure the build command's output directory does not include the repo root (typical cause: `pages_build_output_dir` pointing at `.` or a copy step dragging dotfiles/config along). If a file must exist at output-adjacent paths, add an explicit delete step or `.assetsignore`-style exclusion before deploy.
3. **CI secret-scanning on the config file.** Run a regex/entropy scanner (gitleaks, trufflehog) against `wrangler.toml`/`wrangler.json` in CI so a pasted secret fails the build, and rotate anything that ever touched the file — a served secret must be assumed harvested, per [api-token rotation governance](api-token-least-privilege-and-rotation-governance.md).
4. **Scope the blast radius when a value does leak.** Rotate the secret, check access logs for fetches of the file, and prefer secrets that were scoped least-privilege from day one so a leak is not also an account takeover. See [secrets store binding selection](secrets-store-binding-selection-and-blast-radius-control.md) for binding-level isolation options.

## Related

- `cloudflare/wrangler-toml-reference.md` — config syntax reference (does not cover exposure; this article is the security complement).
- `cloudflare/pages-best-practices.md`, `cloudflare/pages-headers-config.md` — Pages output hygiene.
