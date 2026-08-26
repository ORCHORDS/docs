# react-native-splash-screen

**Issue:** Displaying a native splash screen while the JS bundle loads in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without a splash screen, users see a white/black flash while the bundle initializes; native splash screens bridge this gap.

## Pattern / Solution
```sh
npm install react-native-splash-screen
npx pod-install
```

iOS — `AppDelegate.mm`:
```objc
#import "RNSplashScreen.h"

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
  // ... RN setup
  [RNSplashScreen show];
  return YES;
}
```

Android — `MainActivity.java`:
```java
import org.devio.rn.splashscreen.SplashScreen;

@Override
protected void onCreate(Bundle savedInstanceState) {
  SplashScreen.show(this);
  super.onCreate(savedInstanceState);
}
```

React Native — hide after app is ready:
```ts
import SplashScreen from 'react-native-splash-screen';
import { useEffect } from 'react';

function App() {
  useEffect(() => {
    // Hide after fonts, data, or auth check
    SplashScreen.hide();
  }, []);
  return <Navigator />;
}
```

For Expo, use `expo-splash-screen`:
```ts
import * as SplashScreen from 'expo-splash-screen';
SplashScreen.preventAutoHideAsync();
// later:
await SplashScreen.hideAsync();
```

## Gotchas
- Forgetting to call `hide()` leaves the splash screen up permanently
- The splash image must be placed in `android/app/src/main/res/drawable/` and iOS `LaunchScreen.storyboard`
- Android 12+ ignores the old `SplashScreen` API; use the new `androidx.core:core-splashscreen` library
- Animated splash screens on Android require a `windowBackground` theme, not a layout file

## Related
- `react-native-app-icon-generation.md`
- `react-native-dark-mode.md`
