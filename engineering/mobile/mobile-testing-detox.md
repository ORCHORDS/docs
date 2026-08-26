# mobile-testing-detox

**Issue:** Running end-to-end UI tests on React Native apps with Detox on real device simulators
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Detox synchronizes with the JS event loop and native animations before asserting, eliminating flaky `waitFor` sleep hacks.

## Pattern / Solution
```sh
npm install detox --save-dev
detox init
```

`.detoxrc.js`:
```js
module.exports = {
  testRunner: { args: { $0: 'jest', config: 'e2e/jest.config.js' } },
  apps: {
    'ios.debug': { type: 'ios.app', binaryPath: 'ios/build/MyApp.app', build: 'xcodebuild ...' },
    'android.debug': { type: 'android.apk', binaryPath: 'android/app/build/outputs/apk/debug/app-debug.apk' },
  },
  devices: {
    simulator: { type: 'ios.simulator', device: { type: 'iPhone 15' } },
    emulator: { type: 'android.emulator', device: { avdName: 'Pixel_6_API_33' } },
  },
  configurations: {
    'ios.sim.debug': { device: 'simulator', app: 'ios.debug' },
    'android.emu.debug': { device: 'emulator', app: 'android.debug' },
  },
};
```

`e2e/login.test.ts`:
```ts
import { device, element, by, expect } from 'detox';

describe('Login', () => {
  beforeAll(async () => { await device.launchApp(); });
  beforeEach(async () => { await device.reloadReactNative(); });

  it('should login with valid credentials', async () => {
    await element(by.id('email-input')).typeText('user@example.com');
    await element(by.id('password-input')).typeText('password123');
    await element(by.id('login-button')).tap();
    await expect(element(by.id('home-screen'))).toBeVisible();
  });
});
```

## Gotchas
- Add `testID` props to RN components to target them in Detox — CSS selectors don't exist
- Detox requires the app to be built in release-like mode (`detox build`) before running tests
- On Android, enable the emulator with hardware acceleration (`-gpu host`) or tests are extremely slow
- Network requests in tests should use a mock server (Nock/MSW) to avoid flakiness from real APIs

## Related
- `mobile-e2e-testing.md`
- `mobile-testing-jest.md`
- `react-native-testing-patterns.md`
