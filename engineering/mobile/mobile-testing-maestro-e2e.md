# Maestro E2E Testing for React Native Apps

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your Detox or Appium suite is brittle, slow to iterate, and requires native build knowledge to debug.
New team members bounce off the XML-based locators and async timing APIs. CI times balloon past
20 minutes for a 40-flow suite. You want declarative, YAML-based flows that non-engineers can read
and tweak, fast device-side execution, and first-class Expo support without ejecting.

## Context

Maestro (by mobile.dev) is an open-source E2E framework that drives real devices and simulators
through a YAML DSL executed directly on the device. Unlike Detox, it does not require rebuilding
the native app to change tests; unlike Appium, it does not route through a remote WebDriver server.
Flows are stored as `.yaml` files, run with `maestro test <file>`, and produce video replays plus
structured JSON reports. As of 2026, Maestro Cloud offers hosted device farms; self-hosted
runners integrate natively with GitHub Actions and Expo EAS.

Maestro targets:
- React Native (Expo and bare workflow)
- Flutter
- iOS native (SwiftUI, UIKit)
- Android native (Compose, Views)

---

## 1. Installation and Initial Setup

```bash
# macOS / Linux
curl -Ls "https://get.maestro.mobile.dev" | bash

# Verify
maestro --version   # 1.38+ recommended

# Connect a device or start a simulator, then run a single flow
maestro test flows/login.yaml
```

For CI, the GitHub Actions step is:

```yaml
# .github/workflows/e2e.yml
- name: Install Maestro
  run: |
    curl -Ls "https://get.maestro.mobile.dev" | bash
    echo "$HOME/.maestro/bin" >> $GITHUB_PATH

- name: Run Maestro suite
  run: maestro test flows/ --format junit --output report.xml
  env:
    MAESTRO_DRIVER_STARTUP_TIMEOUT: 90000
```

For Expo EAS builds, add the `maestro` build profile:

```json
// eas.json
{
  "build": {
    "e2e": {
      "distribution": "internal",
      "ios": { "simulator": true },
      "android": { "buildType": "apk" },
      "env": { "MAESTRO": "1" }
    }
  }
}
```

---

## 2. Writing Your First Flows

Maestro flows are YAML files. Each step is an action. The framework automatically retries element
lookups for up to 40 seconds by default, eliminating most timing-related flakiness.

```yaml
# flows/login.yaml
appId: com.orchords.app
---
- launchApp
- tapOn:
    text: "Sign in with email"
- inputText: "test@example.com"
- tapOn:
    id: "password-input"
- inputText: "S3cur3Pass!"
- tapOn:
    text: "Log In"
- assertVisible:
    text: "Welcome back"
- takeScreenshot: login_success
```

### Element selectors

Maestro supports several locator strategies; prefer `id` over text for stability:

```yaml
# By testID / accessibility label (preferred)
- tapOn:
    id: "submit-button"

# By visible text (fragile across locales — avoid in multilingual apps)
- tapOn:
    text: "Continue"

# By index when multiple matches exist
- tapOn:
    text: "Item"
    index: 2

# Scroll until element is visible
- scrollUntilVisible:
    element:
      id: "terms-checkbox"
    direction: DOWN
    timeout: 10000
```

In React Native, set `testID` on any pressable or View:

```tsx
<Pressable testID="submit-button" onPress={handleSubmit}>
  <Text>Submit</Text>
</Pressable>
```

---

## 3. Subflows, Environment Variables, and Parametrized Flows

Complex suites reuse login steps and test-data setup through subflows and env substitution.

```yaml
# flows/_shared/login.yaml  (underscore prefix = subflow, not run standalone)
appId: com.orchords.app
---
- tapOn:
    text: "Sign in with email"
- inputText: "${EMAIL}"
- tapOn:
    id: "password-input"
- inputText: "${PASSWORD}"
- tapOn:
    text: "Log In"
- assertVisible:
    id: "home-screen"
```

```yaml
# flows/post_creation.yaml
appId: com.orchords.app
---
- launchApp:
    clearState: true
- runFlow:
    file: _shared/login.yaml
    env:
      EMAIL: ${TEST_EMAIL}
      PASSWORD: ${TEST_PASSWORD}
- tapOn:
    id: "create-post-fab"
- inputText: "Hello from Maestro"
- tapOn:
    id: "publish-button"
- assertVisible:
    text: "Hello from Maestro"
```

Run with environment variables injected from CI secrets:

```bash
maestro test flows/post_creation.yaml \
  -e TEST_EMAIL=robot@example.com \
  -e TEST_PASSWORD=AutomationPass1
```

### Conditional assertions

```yaml
# Assert element NOT visible
- assertNotVisible:
    id: "error-banner"

# Wait for element and fail if not seen
- extendedWaitUntil:
    visible:
      id: "feed-list"
    timeout: 15000
```

---

## 4. Network Interception and Test Data Seeding

Maestro does not natively proxy HTTP, but you can combine it with a local mock server or
WireMock container that the app points to via `MAESTRO=1` env var at build time.

```tsx
// app/api/client.ts
const BASE_URL = process.env.MAESTRO
  ? "http://localhost:8080"          // WireMock
  : "https://api.example.com";
```

```yaml
# flows/feed_error_state.yaml
appId: com.orchords.app
---
- launchApp:
    clearState: true
    arguments:
      FORCE_FEED_ERROR: "true"
- runFlow:
    file: _shared/login.yaml
    env:
      EMAIL: test@example.com
      PASSWORD: pass
- assertVisible:
    text: "Failed to load feed"
- tapOn:
    text: "Retry"
```

App-side, read launch arguments in React Native:

```tsx
import { NativeModules } from "react-native";

const { FORCE_FEED_ERROR } = NativeModules.RNLaunchArguments ?? {};
```

---

## 5. CI Integration and Reporting

```yaml
# .github/workflows/maestro.yml
name: Maestro E2E

on: [push, pull_request]

jobs:
  e2e-ios:
    runs-on: macos-15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
      - run: npm ci
      - name: Boot simulator
        run: |
          xcrun simctl boot "iPhone 16 Pro"
          open -a Simulator
      - name: Build Expo dev client
        run: npx expo run:ios --device "iPhone 16 Pro" --no-bundler
      - name: Install Maestro
        run: curl -Ls "https://get.maestro.mobile.dev" | bash
      - name: Run flows
        run: |
          ~/.maestro/bin/maestro test flows/ \
            --format junit \
            --output maestro-report.xml
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: maestro-report
          path: maestro-report.xml
```

Maestro Cloud (SaaS) removes the need for self-hosted macOS runners:

```bash
# Upload and run on Maestro Cloud
maestro cloud --apiKey $MAESTRO_API_KEY flows/
```

---

## Anti-patterns

- **Using text selectors for buttons** — breaks on locale changes and A/B copy tests. Always
  set `testID` on interactive elements and use `id:` locators.
- **No `clearState: true` on launchApp** — residual session state causes flaky inter-flow
  failures, especially for auth gates.
- **Asserting pixel-perfect screenshots** — Maestro `takeScreenshot` is for debugging, not
  visual regression. Use Storybook + Chromatic or Percy for pixel diffing.
- **Giant monolithic flows** — a 200-step flow is hard to debug. Decompose into subflows of
  5–15 steps each.
- **Forgetting to set `MAESTRO_DRIVER_STARTUP_TIMEOUT`** — cold Expo dev clients on slow CI
  runners miss the default 60 s boot window.

---

## Gotchas

- **Android emulator AVD must use x86_64 images** on ARM Mac GitHub-hosted runners via
  Rosetta; arm64 images crash Maestro's ADB bridge as of 1.38.
- **iOS simulators only** — Maestro does not support iOS physical device testing in CI
  without a dedicated Maestro Cloud device slot or a locally-managed device farm.
- **Keyboard dismiss** — React Native's `dismissKeyboard` is not exposed as a Maestro action;
  use `tapOn` outside the input or `hideKeyboard` (added in Maestro 1.36):

  ```yaml
  - hideKeyboard
  ```

- **Metro bundler must be running** for Expo dev client flows; add a `npx expo start &` step
  before launching the simulator in CI.
- **`scrollUntilVisible` terminates after 50 scroll steps** by default — pass
  `maxScrollCount: 100` for long lists.

---

## Verification

```bash
# Run a single flow and watch live
maestro test flows/login.yaml --continuous

# List all flows that will run
maestro test flows/ --dry-run

# Generate HTML report
maestro test flows/ --format html --output report/

# Record a video of the run
maestro record flows/login.yaml
```

Expected output for a passing suite:

```
✅  login                      2.1s
✅  post_creation               5.4s
✅  feed_error_state            3.9s
─────────────────────────────────────
3 flows, 3 passed, 0 failed
```

---

## Related

- `mobile-e2e-testing.md` — comparative overview of Detox vs. Appium vs. Maestro
- `mobile-testing-detox.md` — Detox-specific setup and patterns
- `expo-eas-build-cloudflare-workers-secrets.md` — injecting secrets into EAS builds
- `mobile-ci-cd-github-actions.md` — general mobile CI patterns
- `react-native-testing-patterns.md` — unit and integration testing with Jest

## Sources

- Maestro documentation: https://maestro.mobile.dev/docs
- Maestro GitHub: https://github.com/mobile-dev-inc/maestro
- Expo E2E testing guide: https://docs.expo.dev/build-reference/e2e-tests/
- GitHub Actions macOS runner availability: https://github.com/actions/runner-images
