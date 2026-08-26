# mobile-ci-cd-github-actions

**Issue:** Running iOS and Android build and test pipelines on GitHub Actions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
iOS builds require macOS runners (expensive); splitting build stages minimizes costly runner minutes.

## Pattern / Solution
`.github/workflows/ios.yml`:
```yaml
name: iOS CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: macos-14
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - run: npx pod-install ios
        working-directory: ios
      - name: Run unit tests
        run: xcodebuild test -workspace ios/MyApp.xcworkspace -scheme MyApp -destination 'platform=iOS Simulator,name=iPhone 15'
      - name: Build release
        env:
          MATCH_PASSWORD: ${{ secrets.MATCH_PASSWORD }}
          FASTLANE_APPLE_APPLICATION_SPECIFIC_PASSWORD: ${{ secrets.ASC_PASSWORD }}
        run: cd ios && bundle exec fastlane beta
```

`.github/workflows/android.yml`:
```yaml
name: Android CI
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with: { distribution: 'temurin', java-version: '17' }
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm ci
      - name: Build AAB
        run: cd android && ./gradlew bundleRelease
        env:
          KEYSTORE_PASSWORD: ${{ secrets.KEYSTORE_PASSWORD }}
```

## Gotchas
- Cache `~/.gradle/caches` and `node_modules` to cut build times by 50%
- `macos-14` runners cost ~10× more than `ubuntu-latest`; run only what requires macOS there
- Secrets must be set in `Settings > Secrets and variables > Actions`; they cannot be read by forks
- `actions/cache` invalidation key must include lock file hash to avoid stale dependency cache

## Related
- `mobile-ci-cd-fastlane.md`
- `react-native-build-variants.md`
