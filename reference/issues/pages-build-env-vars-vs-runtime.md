# pages-build-env-vars-vs-runtime

**Issue:** Cloudflare Pages build-time environment variables are not automatically available at runtime in Pages Functions
**Date:** 2026-08-11
**Status:** documented

## Symptom
A secret set in the Cloudflare Pages dashboard under "Environment variables" is available during the build (e.g., in `vite.config.ts` via `process.env.MY_VAR`) but `undefined` at runtime in a Pages Function (`/functions/*.ts`).

## Root cause
Pages has two categories of environment variables: build-time (injected into the build process via Node.js `process.env`) and runtime (bound as Worker bindings, available in `context.env`). These are configured separately in the dashboard and serve different purposes.

## Fix
For runtime secrets in Pages Functions, add them under "Functions" → "Environment variables" in the Pages project settings, not only under "Build" settings. Access them via:
```ts
export async function onRequest(context: EventContext<Env, string, unknown>) {
  const secret = <redacted-secret> // runtime binding, not process.env
}
```

## Detection
```
grep -rn "process.env" functions/ --include="*.ts"
```
Any `process.env` reference inside `functions/` is a bug — it will be `undefined` at runtime.

## Related
- `wrangler-dev-vs-prod-bindings.md`
- `vite-env-types-conflict.md`
