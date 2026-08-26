# android-deep-linking-intents

**Issue:** Configuring Android intent filters for deep links and App Links
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Android deep linking uses intent filters in the manifest. App Links (verified HTTPS) are more secure than custom schemes. Without domain verification, other apps can intercept your links.

## Pattern / Solution
**AndroidManifest.xml intent filters:**
```xml
<activity android:name=".MainActivity" android:launchMode="singleTop">
    <!-- Custom scheme -->
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="myapp" />
    </intent-filter>

    <!-- App Links (verified HTTPS) -->
    <intent-filter android:autoVerify="true">
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="example.com" android:pathPrefix="/product" />
    </intent-filter>
</activity>
```

**Digital Asset Links file** at `https://example.com/.well-known/assetlinks.json`:
```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.example.myapp",
    "sha256_cert_fingerprints": ["AA:BB:CC:..."]
  }
}]
```

**Get SHA-256 fingerprint:**
```bash
keytool -list -v -keystore my-release-key.jks -alias my-key-alias
# Or for Play App Signing — get from Play Console → Setup → App Integrity
```

**Handle intent in React Native:**
```ts
import { Linking } from 'react-native';
const url = await Linking.getInitialURL(); // cold start
Linking.addEventListener('url', ({ url }) => handleLink(url)); // warm start
```

**Test App Links:**
```bash
adb shell pm get-app-links --package com.example.myapp
adb shell am start -a android.intent.action.VIEW -d "https://example.com/product/42" com.example.myapp
```

## Gotchas
- `autoVerify` verification runs once at install; if it fails (e.g., file not found), links fall back to the browser chooser
- Play App Signing changes your signing key — update `assetlinks.json` with the Play-issued fingerprint, not your local keystore
- `android:launchMode="singleTop"` prevents multiple activity instances when tapping links; override `onNewIntent` to handle the link
- Links from Gmail on Android do not trigger App Links in older versions; test across email clients
- Without `autoVerify`, all apps that match the intent filter are shown in a disambiguation dialog

## Related
- `react-native-deep-linking.md`
- `ios-universal-links.md`
- `mobile-deep-link-hijacking.md`
