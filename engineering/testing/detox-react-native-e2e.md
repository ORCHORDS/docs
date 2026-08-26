# detox-react-native-e2e

**Issue:** End-to-end testing React Native apps with Detox
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Playwright and Cypress cannot test native mobile apps. Detox runs tests against real devices or simulators.

## Pattern / Solution
```bash
npm install -D detox @types/detox
```

`.detoxrc.js`:
```js
module.exports = {
  testRunner: { args: { $0: "jest", config: "e2e/jest.config.js" } },
  apps: {
    "ios.debug": { type: "ios.app", binaryPath: "ios/build/YourApp.app", build: "..." },
  },
  devices: {
    simulator: { type: "ios.simulator", device: { type: "iPhone 15" } },
  },
  configurations: {
    "ios.sim.debug": { device: "simulator", app: "ios.debug" },
  },
};
```

Test file:
```ts
import { device, element, by, expect as detoxExpect } from "detox";

describe("Login flow", () => {
  beforeAll(async () => await device.launchApp());
  beforeEach(async () => await device.reloadReactNative());

  it("logs in with valid credentials", async () => {
    await element(by.id("email-input")).typeText("user@example.com");
    await element(by.id("password-input")).typeText("password");
    await element(by.id("login-button")).tap();
    await detoxExpect(element(by.id("dashboard"))).toBeVisible();
  });
});
```

## Gotchas
- Detox requires a debug build with specific configuration
- Tests run slower than web e2e — budget 30-60 min for full suite
- `testID` props must be added to React Native components

## Related
- `end-to-end-test-strategy.md`
- `mobile-browser-testing.md`
