# mobile-e2e-testing

**Issue:** Strategy and tooling for end-to-end mobile testing across iOS and Android
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Unit tests pass but integration failures between the native layer and JS business logic only surface in production.

## Pattern / Solution
Tool selection:
| Tool | Best for |
|------|----------|
| Detox | React Native apps, tight JS sync |
| Appium | Cross-platform, native apps |
| Maestro | Fast YAML-based flows, quick iteration |

Maestro example (no code required):
```yaml
# flows/login.yaml
appId: com.example.myapp
---
- launchApp
- tapOn: "Email"
- inputText: "user@example.com"
- tapOn: "Password"
- inputText: "password123"
- tapOn: "Log In"
- assertVisible: "Welcome, User"
```

```sh
maestro test flows/login.yaml
maestro cloud --apiKey $MAESTRO_KEY flows/
```

E2E test pyramid:
- 70% unit + integration (Jest/RNTL)
- 20% Detox/Maestro for critical user journeys (login, checkout, onboarding)
- 10% manual exploratory testing

## Gotchas
- E2E tests are the slowest and most brittle layer; keep the suite small and focused on happy paths
- Network calls in E2E tests should be real or recorded (VCR cassettes) — mocking at the JS layer defeats the purpose
- Run E2E tests on physical device farms (BrowserStack App Automate, Firebase Test Lab) for reliability
- Reset app state (`device.launchApp({ newInstance: true })`) between each test to prevent pollution

## Related
- `mobile-testing-detox.md`
- `mobile-testing-jest.md`
- `mobile-ci-cd-github-actions.md`
