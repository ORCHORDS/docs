# vite-env-variables

**Issue:** Environment variables in Vite have different exposure rules than webpack/CRA
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
process.env.REACT_APP_* from CRA does not work; secrets leak into the client bundle.

## Pattern / Solution
```
# .env.local
VITE_API_URL=https://api.example.com
SECRET_KEY=never_exposed          # no VITE_ prefix; server only
```

```ts
// Client code
const url = import.meta.env.VITE_API_URL;

// TypeScript types
// src/vite-env.d.ts
interface ImportMetaEnv {
  readonly VITE_API_URL: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

## Gotchas
- Only VITE_-prefixed variables are exposed to the client bundle
- .env.local is not committed; .env.example documents required vars
- import.meta.env.MODE is 'development' | 'production' | 'test'
- process.env is not available; always use import.meta.env

## Related
- `vite-config-patterns.md`
- `esbuild-transform-api.md`
