# vite-config-patterns

**Issue:** Default Vite config needs tuning for aliases, proxies, and build targets
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Absolute imports fail; API calls hit CORS in dev; the build targets modern browsers by default.

## Pattern / Solution
```ts
// vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    proxy: {
      '/api': { target: 'http://localhost:3001', changeOrigin: true },
    },
  },
  build: {
    target: 'es2020',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: { vendor: ['react', 'react-dom'] },
      },
    },
  },
});
```

## Gotchas
- path.resolve requires __dirname; use import.meta.dirname in ESM
- Proxy only works in dev; production needs a real reverse proxy
- target: 'esnext' enables top-level await and import.meta

## Related
- `vite-env-variables.md`
- `vite-plugin-development.md`
