# react-native-deep-linking

**Issue:** Handling deep links and universal links in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Deep links open the app to a specific screen from a URL. They come in two flavors: custom scheme (`myapp://product/42`) and universal/app links (`https://example.com/product/42`). The latter requires server-side verification files.

## Pattern / Solution
**Expo Router handles deep links automatically** via the file structure. Configure the scheme in `app.json`:
```json
{
  "expo": {
    "scheme": "myapp",
    "intentFilters": [
      {
        "action": "VIEW",
        "autoVerify": true,
        "data": [{ "scheme": "https", "host": "example.com", "pathPrefix": "/" }],
        "category": ["BROWSABLE", "DEFAULT"]
      }
    ]
  }
}
```

**React Navigation linking config:**
```ts
const linking: LinkingOptions<RootStackParamList> = {
  prefixes: ['myapp://', 'https://example.com'],
  config: {
    screens: {
      Home: '',
      Product: 'product/:id',
      Profile: 'user/:username',
    },
  },
};

<NavigationContainer linking={linking}>
```

**Handle links manually (bare RN):**
```ts
import { Linking } from 'react-native';

// Cold start
const initialUrl = await Linking.getInitialURL();
if (initialUrl) handleDeepLink(initialUrl);

// Warm start
const sub = Linking.addEventListener('url', ({ url }) => handleDeepLink(url));
```

**AASA file (iOS Universal Links)** at `/.well-known/apple-app-site-association`:
```json
{
  "applinks": {
    "apps": [],
    "details": [{ "appID": "TEAMID.com.example.myapp", "paths": ["/product/*", "/user/*"] }]
  }
}
```

## Gotchas
- Custom URI schemes can be hijacked by other apps; prefer universal/app links for sensitive flows (OAuth redirects, password reset)
- AASA must be served with `Content-Type: application/json` and no redirect on the `/.well-known/` path
- iOS caches AASA aggressively; changes can take 24–48 hours to propagate without a device reinstall
- Android `autoVerify` requires the `.well-known/assetlinks.json` file; verify with `adb shell pm get-app-links`
- Deep links don't work in Expo Go for custom schemes unless using `exp://` tunnel URL during development

## Related
- `react-native-navigation-patterns.md`
- `ios-universal-links.md`
- `android-deep-linking-intents.md`
- `mobile-deep-link-hijacking.md`
