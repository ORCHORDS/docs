# react-native-image-picker

**Issue:** Picking images/videos from the device library or camera in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Accessing photo library or camera requires runtime permissions and differs significantly between iOS and Android.

## Pattern / Solution
```sh
npm install react-native-image-picker
# iOS
npx pod-install
```

Add to `Info.plist`:
```xml
<key>NSPhotoLibraryUsageDescription</key>
<string>Select photos to upload</string>
<key>NSCameraUsageDescription</key>
<string>Take photos for your profile</string>
```

Add to `AndroidManifest.xml`:
```xml
<uses-permission android:name="android.permission.READ_MEDIA_IMAGES" />
<uses-permission android:name="android.permission.CAMERA" />
```

```js
import { launchImageLibrary, launchCamera } from 'react-native-image-picker';

async function pickImage() {
  const result = await launchImageLibrary({
    mediaType: 'photo',
    quality: 0.8,
    selectionLimit: 1,
    includeBase64: false,
  });

  if (!result.didCancel && !result.errorCode) {
    const asset = result.assets[0];
    console.log(asset.uri, asset.width, asset.height);
  }
}
```

## Gotchas
- On Android 13+ use `READ_MEDIA_IMAGES` instead of `READ_EXTERNAL_STORAGE`
- `includeBase64: true` with large images causes memory crashes — upload via URI instead
- iOS returns `ph://` URIs that cannot be directly used with `fetch`; use `uri` from assets
- `selectionLimit: 0` means unlimited on iOS but may not work on all Android versions

## Related
- `react-native-camera-permissions.md`
- `mobile-image-caching-patterns.md`
