# vitest-setup

**Issue:** Configuring Vitest as a Jest replacement with TypeScript and Vite
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Migrating from Jest to Vitest or starting a new project with Vite and needing fast, native ESM tests.

## Pattern / Solution
```bash
npm install -D vitest @vitest/ui happy-dom
```

`vite.config.ts` (or `vitest.config.ts`):
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom", // or "jsdom"
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      thresholds: { lines: 80, branches: 80 },
    },
  },
});
```

`src/test/setup.ts`:
```ts
import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);
```

## Gotchas
- `globals: true` needed to use `describe`/`it`/`expect` without imports
- `happy-dom` is faster than `jsdom` but has less API coverage
- Vitest uses Vite transforms — no separate babel config needed

## Related
- `jest-configuration-typescript.md`
- `vitest-coverage-v8.md`
