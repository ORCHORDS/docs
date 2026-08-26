# react-native-build-variants

**Issue:** Configuring separate debug, staging, and production builds with different API endpoints and bundle IDs
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Shipping with hardcoded staging URLs or mixing production credentials with test accounts causes critical bugs.

## Pattern / Solution
Use `react-native-config` for env-based configuration:
```sh
npm install react-native-config
npx pod-install
```

`.env.production`:
```
API_URL=https://api.example.com
APP_ENV=production
```
`.env.staging`:
```
API_URL=https://staging-api.example.com
APP_ENV=staging
```

```ts
import Config from 'react-native-config';
const baseUrl = Config.API_URL;
```

Android — in `app/build.gradle`:
```groovy
android {
  flavorDimensions "environment"
  productFlavors {
    staging {
      applicationIdSuffix ".staging"
      resValue "string", "app_name", "MyApp Staging"
    }
    production {
      // no suffix
    }
  }
}
```

iOS — duplicate the scheme in Xcode, set different Bundle IDs per scheme, add pre-action to copy the right `.env` file:
```sh
# Build Pre-action script
cp "${PROJECT_DIR}/../.env.production" "${PROJECT_DIR}/../.env"
```

## Gotchas
- `.env` files should never be committed; add them to `.gitignore`
- `react-native-config` variables are baked in at build time, not runtime — changing `.env` requires a rebuild
- Android product flavors and iOS schemes must both be configured or CI builds will use the wrong values
- Bundle IDs must differ per environment to install them side-by-side on the same device

## Related
- `mobile-ci-cd-fastlane.md`
- `mobile-ci-cd-github-actions.md`
- `react-native-code-push.md`
