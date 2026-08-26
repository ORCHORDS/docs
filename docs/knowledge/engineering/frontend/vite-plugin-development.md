# vite-plugin-development

**Issue:** Custom transform or virtual module behavior needs a Vite plugin
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Auto-generating route manifests from filesystem or injecting build metadata into the bundle.

## Pattern / Solution
```ts
import type { Plugin } from 'vite';

function buildMetaPlugin(): Plugin {
  return {
    name: 'build-meta',
    resolveId(id) {
      if (id === 'virtual:build-meta') return '\0virtual:build-meta';
    },
    load(id) {
      if (id === '\0virtual:build-meta') {
        return `export const BUILD_TIME = '${new Date().toISOString()}';`;
      }
    },
    transform(code, id) {
      if (!id.endsWith('.tsx')) return;
      return code; // return null to skip
    },
  };
}
```

## Gotchas
- Virtual module IDs must be prefixed with \0 in the resolved ID to avoid conflicts
- Use enforce: 'pre' or 'post' to control execution order relative to core transforms
- Vite plugins are a superset of Rollup plugins

## Related
- `vite-config-patterns.md`
- `rollup-library-bundling.md`
