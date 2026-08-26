# jest-configuration-typescript

**Issue:** Setting up Jest with TypeScript, path aliases, and module transforms
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`SyntaxError: Cannot use import statement` or path aliases not resolving in Jest when using TypeScript.

## Pattern / Solution
```bash
npm install -D jest ts-jest @types/jest
```

`jest.config.ts`:
```ts
import type { Config } from "jest";

const config: Config = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/src"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  collectCoverageFrom: ["src/**/*.ts", "!src/**/*.d.ts"],
  coverageThreshold: {
    global: { branches: 80, functions: 80, lines: 80, statements: 80 },
  },
};

export default config;
```

For ESM projects use `ts-jest/presets/default/jest-preset` or switch to Vitest.

## Gotchas
- `ts-jest` and `babel-jest` should not both transform the same files
- `moduleNameMapper` must match `tsconfig.json` `paths` exactly
- `testEnvironment: "jsdom"` needed for DOM/React tests

## Related
- `vitest-setup.md`
- `jest-module-mocking.md`
