# react-native-camera-permissions

**Issue:** Requesting and handling camera and microphone permissions across iOS and Android
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Failing to request permissions at the right time results in silent denials or app rejection in store review.

## Pattern / Solution
```sh
npm install react-native-permissions
npx pod-install
```

`ios/Podfile` — add permissions pod:
```ruby
permissions_path = '../node_modules/react-native-permissions/ios'
pod 'Permission-Camera', :path => "#{permissions_path}/Camera"
pod 'Permission-Microphone', :path => "#{permissions_path}/Microphone"
```

```js
import { check, request, PERMISSIONS, RESULTS } from 'react-native-permissions';
import { Platform } from 'react-native';

const CAMERA_PERMISSION = Platform.select({
  ios: PERMISSIONS.IOS.CAMERA,
  android: PERMISSIONS.ANDROID.CAMERA,
});

async function ensureCameraPermission() {
  const status = await check(CAMERA_PERMISSION);

  if (status === RESULTS.GRANTED) return true;

  if (status === RESULTS.DENIED) {
    const result = await request(CAMERA_PERMISSION);
    return result === RESULTS.GRANTED;
  }

  if (status === RESULTS.BLOCKED) {
    // Direct user to settings — cannot re-prompt
    Linking.openSettings();
    return false;
  }

  return false;
}
```

## Gotchas
- Once `BLOCKED`, `request()` silently no-ops — you must open Settings
- iOS only shows the permission dialog once; subsequent calls to `request()` return `BLOCKED`
- Android 12+ splits camera permission from nearby-devices; check both if using Bluetooth
- Testing on a simulator resets permission state; use a real device for permission flows

## Related
- `react-native-image-picker.md`
- `mobile-gdpr-mobile.md`
