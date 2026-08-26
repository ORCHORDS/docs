# react-native-maps-integration

**Issue:** Embedding interactive maps with markers and regions in React Native apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`react-native-maps` renders a blank white view or crashes on Android without the correct Google Maps API key configuration.

## Pattern / Solution
```sh
npm install react-native-maps
npx pod-install
```

Android `AndroidManifest.xml`:
```xml
<meta-data
  android:name="com.google.android.geo.API_KEY"
  android:value="${MAPS_API_KEY}" />
```

`android/app/build.gradle`:
```groovy
defaultConfig {
  manifestPlaceholders = [MAPS_API_KEY: project.env.get("MAPS_API_KEY")]
}
```

```jsx
import MapView, { Marker, PROVIDER_GOOGLE } from 'react-native-maps';

<MapView
  provider={PROVIDER_GOOGLE}
  style={{ flex: 1 }}
  initialRegion={{
    latitude: 37.78825,
    longitude: -122.4324,
    latitudeDelta: 0.0922,
    longitudeDelta: 0.0421,
  }}
  onRegionChangeComplete={(region) => console.log(region)}
>
  <Marker
    coordinate={{ latitude: 37.78825, longitude: -122.4324 }}
    title="My Location"
    description="Subtitle here"
  />
</MapView>
```

## Gotchas
- iOS uses Apple Maps by default; pass `provider={PROVIDER_GOOGLE}` explicitly for Google Maps
- `latitudeDelta` / `longitudeDelta` control zoom level — smaller values = more zoomed in
- Map must have a defined `style` with non-zero dimensions or it renders invisible
- Expo Go does not support `react-native-maps` with Google provider; use a dev build

## Related
- `react-native-camera-permissions.md`
- `mobile-network-resilience.md`
