# Expo Router — File-Based Routing, Typed Routes, and Deep Linking

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your React Native app uses React Navigation with a 200-line
`linking.ts` configuration for deep links. Adding a new screen
requires editing three files: the screen component, the navigator
stack, and the linking config. A marketing team sends a deep link
campaign to `myapp://products/123` but it opens a blank screen
because the linking config was not updated after a route refactor.
Meanwhile, universal links on iOS fail silently because the
`apple-app-site-association` file was never deployed.

## Context

Expo Router brings file-based routing to React Native, where files
in the `app/` directory automatically become routes — identical
URL paths work on web, iOS, and Android. Every screen is deep-
linkable by default without a separate linking configuration.
Typed routes (beta, widely used) auto-generate route and param
types for compile-time safety. Deep linking requires configuring
`scheme` for custom URL schemes (`myapp://`) and associated
domains/intent filters for universal links (`https://example.com`).
Migration from React Navigation replaces route props with the
`useLocalSearchParams()` hook.

## File-based routing

```
app/
  _layout.tsx          → Root layout (wraps all routes)
  index.tsx            → /
  about.tsx            → /about
  settings/
    _layout.tsx        → Settings layout (tab navigator, etc.)
    index.tsx          → /settings
    profile.tsx        → /settings/profile
  user/
    [id].tsx           → /user/123 (dynamic route)
  [...missing].tsx     → Catch-all (404)

Rules:
  → File path = URL path (web, iOS, Android)
  → _layout.tsx files define navigation structure
  → [param].tsx for dynamic segments
  → [...rest].tsx for catch-all routes
  → Every route is deep-linkable by default
```

## Typed routes

```json
// app.json — enable typed routes
{
  "expo": {
    "experiments": {
      "typedRoutes": true
    }
  }
}
```

```typescript
// Compile-time-safe navigation
import { Link } from 'expo-router';

// TypeScript catches invalid routes at compile time
<Link >View User</Link>
<Link href={{ pathname: '/user/[id]', params: { id: '42' } }}>
  View User
</Link>

// Typed params
import { useLocalSearchParams } from 'expo-router';

export default function UserScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <Text>User {id}</Text>;
}
```

## Deep linking configuration

```json
// app.json
{
  "expo": {
    "scheme": "myapp",
    "ios": {
      "associatedDomains": ["applinks:example.com"]
    },
    "android": {
      "intentFilters": [
        {
          "action": "VIEW",
          "autoVerify": true,
          "data": [
            { "scheme": "https", "host": "example.com" }
          ],
          "category": ["BROWSABLE", "DEFAULT"]
        }
      ]
    }
  }
}
```

```
Deep link types:

  Custom scheme:     myapp://user/42
    → Works without domain verification
    → Can be hijacked by other apps with same scheme
    → Use for development and testing

  Universal Links (iOS):
    → https://example.com/user/42 opens app directly
    → Requires apple-app-site-association on domain
    → Fallback to Safari if app not installed

  App Links (Android):
    → https://example.com/user/42 opens app directly
    → Requires assetlinks.json on domain
    → autoVerify: true enables automatic verification
    → Fallback to browser if app not installed

  Domain verification files:
    iOS:  /.well-known/apple-app-site-association
    Android: /.well-known/assetlinks.json
```

## Navigation patterns

```typescript
// useLocalSearchParams — route-scoped (preferred)
// Only re-renders the screen owning the param
const { id } = useLocalSearchParams<{ id: string }>();

// useGlobalSearchParams — root-scoped
// Re-renders on ANY param change across the app
const { id } = useGlobalSearchParams<{ id: string }>();

// Programmatic navigation
import { router } from 'expo-router';

router.push('/user/42');
router.replace('/login');
router.back();

// Navigate with params
router.push({
  pathname: '/user/[id]',
  params: { id: '42' },
});
```

## Migration from React Navigation

```
React Navigation → Expo Router mapping:

  Before                          After
  ──────────────────────────────────────────────────────────
  createStackNavigator()          app/_layout.tsx with <Stack>
  navigation.navigate('User')    router.push('/user/42')
  route.params.id                useLocalSearchParams().id
  linking.ts config              Automatic (file-based)
  NavigationContainer             Not needed (provided by router)
  useNavigation()                 router (from expo-router)
  useRoute()                      useLocalSearchParams()

  Migration steps:
  1. Split screen components into individual files
  2. Match file structure to desired URL paths
  3. Replace route props with useLocalSearchParams()
  4. Remove linking.ts configuration entirely
  5. From SDK 56+: use expo-router entry points,
     not @react-navigation/* imports directly
```

## Anti-patterns

- **Passing objects/functions as route params** — only strings
  can be passed as route parameters (like URL query strings).
  Use a state management library or fetch data by ID in the
  target screen instead of passing complex objects.
- **Returning null from root layout during loading** — common
  React Native pattern for font/asset loading, but unsupported
  in Expo Router. Use `SplashScreen.preventAutoHideAsync()` and
  hide after assets load.
- **Skipping domain verification files** — universal links and
  app links fail silently without AASA/assetlinks.json on the
  domain, falling back to the browser without error messages.
- **Using useGlobalSearchParams everywhere** — causes unnecessary
  re-renders across the entire app when any param changes. Use
  `useLocalSearchParams` (route-scoped) by default.

## Gotchas

- **`autoVerify: true` on Android** — must be set in intent
  filters for App Links verification. Without it, Android shows
  a disambiguation dialog instead of opening the app directly.
- **Category values on Android** — both `BROWSABLE` and `DEFAULT`
  categories are required in intent filters. Missing either causes
  silent link handling failures.
- **`useSearchParams` deprecated** — replaced by
  `useLocalSearchParams` and `useGlobalSearchParams` in newer
  Expo Router versions. Update all usages.
- **SDK 56+ import restrictions** — Expo Router no longer allows
  importing `@react-navigation/*` packages directly. Use the
  matching `expo-router` entry points instead.

## Verification

- File structure in `app/` matches desired URL paths.
- Typed routes enabled and route types auto-generated.
- Custom scheme configured and tested on both platforms.
- AASA and assetlinks.json deployed and verified on domain.
- `useLocalSearchParams` used instead of global variant.
- Deep links tested for all critical user flows.

## Related

- `documentation/docs/policies/mobile/react-native-new-architecture-fabric-jsi.md`
- `documentation/docs/policies/mobile/deep-linking-universal-links-app-links.md`
- `documentation/docs/policies/mobile/app-store-review-compliance.md`

## Source URLs (verified 2026-08-16)

- Introduction to Expo Router — https://docs.expo.dev/router/introduction/
- Typed Routes — https://docs.expo.dev/router/reference/typed-routes/
- Linking, Deep Links, and Universal Links — https://docs.expo.dev/linking/overview/
- Migrate from React Navigation — https://docs.expo.dev/router/migrate/from-react-navigation/
