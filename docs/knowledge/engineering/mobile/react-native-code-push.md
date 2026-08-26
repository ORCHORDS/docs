# react-native-code-push

**Issue:** Delivering JavaScript bundle updates to production React Native apps without a store release
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Bug fixes that only touch JS logic should not require a full app store review cycle; CodePush (App Center) enables silent OTA JS updates.

## Pattern / Solution
```sh
npm install react-native-code-push
npx pod-install
# Register app in App Center
appcenter apps create -p React-Native -o iOS -n MyApp-iOS
appcenter codepush deployment add -a <owner>/MyApp-iOS Production
```

Wrap the root component:
```ts
import CodePush from 'react-native-code-push';

const codePushOptions = {
  checkFrequency: CodePush.CheckFrequency.ON_APP_RESUME,
  installMode: CodePush.InstallMode.ON_NEXT_RESUME,
};

export default CodePush(codePushOptions)(App);
```

Deploy a release:
```sh
appcenter codepush release-react -a <owner>/MyApp-iOS -d Production
```

Mandatory update for critical bugs:
```sh
appcenter codepush release-react -a <owner>/MyApp-iOS -d Production --mandatory
```

## Gotchas
- CodePush **only** updates JS bundle and assets — native code changes require a full store release
- Apple App Store guidelines prohibit CodePush from fundamentally changing app behavior/purpose
- Rollback immediately after a bad deploy: `appcenter codepush rollback -a <owner>/MyApp-iOS Production`
- Using `IMMEDIATE` install mode causes an abrupt restart mid-session — prefer `ON_NEXT_RESUME`

## Related
- `react-native-build-variants.md`
- `react-native-over-the-air-updates.md`
- `mobile-ci-cd-fastlane.md`
