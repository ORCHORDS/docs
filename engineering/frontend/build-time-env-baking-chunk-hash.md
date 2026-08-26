# build-time-env-baking-chunk-hash

**Issue:** A Next.js static-export app deployed to Cloudflare Pages shows stale or missing configuration and mismatched chunk hashes after deploys. Public values read from `process.env` in client code silently bake in at build time, and Turbopack's chunk hashing interacts badly with them. Happened repeatedly on example project (example-org/example-repo) deploys before the pattern was identified.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What actually goes wrong

1. **`process.env.X` in client code is build-time.** The bundler replaces it with a literal during build; a Pages deploy that skipped a rebuild ships the old literal with a new file tree.
2. **Turbopack chunk-hash mismatch.** Env-dependent literals feed into chunk naming; stale cache + new manifest = 404 on chunks or boot with old config.
3. **Symptom is "config drift", not an error.** The app boots fine — with yesterday's API URL or flag — which is worse than crashing because nobody notices.
4. **`.env` files not present in CI** produce `undefined` literals that only fail at runtime on the edge.
5. **CDN caching multiplies it.** Even a correct deploy can serve stale HTML referencing old chunk names unless the CDN is purged.

## The rules that fixed it

1. **Hardcode public values.** Anything the client needs that is not a secret (API origins, public keys, feature flags) gets written as a literal in a committed constants file, not read from env at client runtime.
2. **Secrets stay server-side** in the Worker; the client fetches through routes that inject them.
3. **Clear `.next` (and any build cache) before builds** in CI when env or config changed — incremental builds are where stale literals hide.
4. **Purge the CDN after deploy** when the platform does not auto-invalidate HTML.
5. **Verify the deployed bundle, not the build log** — fetch the live chunk and grep for the expected literal before declaring the deploy good.

## Detection checklist

1. Fetch the live `index.html`, extract the current chunk URLs — do they 200?
2. Fetch a shipped JS chunk and grep for the config literal you expect.
3. Compare the literal against the intended value — drift here is the smoking gun.
4. Check whether the CI build actually re-ran (commit SHA in build output, not just "deployed" event).
5. Only then look at application code — in every observed case the app code was innocent.

## Related

- `../deploy/merged-is-not-deployed-bundle-verification.md`
- `../cloudflare/pages-404-worker-split-diagnosis.md`
