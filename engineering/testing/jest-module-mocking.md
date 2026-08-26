# jest-module-mocking

**Issue:** Mocking ES modules and third-party packages in Jest
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`jest.mock()` calls placed after imports do not mock the module, or named exports are not replaced.

## Pattern / Solution
```ts
// jest.mock is hoisted — place at top, after imports
jest.mock("../lib/mailer", () => ({
  sendEmail: jest.fn().mockResolvedValue(undefined),
}));

// Named export mock
jest.mock("uuid", () => ({ v4: () => "fixed-uuid" }));

// Partial mock — keep real implementation for some exports
jest.mock("../utils", () => ({
  ...jest.requireActual("../utils"),
  formatDate: jest.fn().mockReturnValue("2026-01-01"),
}));

// Mock with factory (avoids hoisting issues)
const mockSend = jest.fn();
jest.mock("../mailer", () => ({ send: mockSend }));
```

Reset in afterEach:
```ts
afterEach(() => jest.clearAllMocks());
```

## Gotchas
- `jest.mock` is hoisted above imports by babel-jest transform
- Dynamic `import()` inside the SUT bypasses static mocks
- ESM modules require `experimental-vm-modules` or Vitest

## Related
- `vitest-setup.md`
- `jest-timer-fakes.md`
