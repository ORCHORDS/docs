# react-native-app-icon-generation

**Issue:** Generating all required app icon sizes for iOS and Android from a single source image
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
iOS requires 20+ icon sizes across different targets (iPhone, iPad, App Store); Android requires adaptive icons with foreground/background layers.

## Pattern / Solution
Use `@bam.tech/react-native-make` or the Expo Image plugin:

```sh
# Expo workflow
npx expo install expo-image

# In app.json
{
  "expo": {
    "icon": "./assets/icon.png",          // 1024x1024 PNG
    "android": {
      "adaptiveIcon": {
        "foregroundImage": "./assets/adaptive-icon.png",
        "backgroundColor": "#ffffff"
      }
    }
  }
}
```

Bare React Native — generate with `react-native-make`:
```sh
npm install -g @bam.tech/react-native-make
react-native set-icon --path ./icon.png --background "#ffffff"
```

Or use the `appicon.co` web tool and place outputs:
- iOS: `ios/<AppName>/Images.xcassets/AppIcon.appiconset/`
- Android: `android/app/src/main/res/mipmap-*/`

## Gotchas
- Source image must be exactly 1024×1024 pixels with no rounded corners (the OS applies masking)
- Transparent PNG backgrounds turn black on Android; use a solid background or adaptive icon
- iOS rejects icons with alpha channel in the App Store submission
- Android 26+ uses adaptive icons; older devices fall back to the `mipmap-*/ic_launcher.png` file

## Related
- `react-native-splash-screen.md`
- `react-native-build-variants.md`
- `mobile-ci-cd-fastlane.md`
