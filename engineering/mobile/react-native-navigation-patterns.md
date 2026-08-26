# react-native-navigation-patterns

**Issue:** Choosing and implementing navigation in React Native (React Navigation vs Expo Router)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React Native has no built-in navigation. The two dominant approaches are React Navigation (imperative, library-based) and Expo Router (file-system-based, like Next.js). Wrong choices lead to deeply nested prop drilling or hard-to-debug deep link handling.

## Pattern / Solution
**Expo Router (preferred for new projects):**
```
app/
  _layout.tsx        ← root layout (Stack/Tabs)
  index.tsx          ← matches /
  (tabs)/
    _layout.tsx      ← tab bar config
    home.tsx         ← matches /home
    profile.tsx
  product/
    [id].tsx         ← matches /product/:id
```

```tsx
// app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router';
export default function TabLayout() {
  return (
    <Tabs screenOptions={{ headerShown: false }}>
      <Tabs.Screen name="home" options={{ title: 'Home' }} />
      <Tabs.Screen name="profile" options={{ title: 'Profile' }} />
    </Tabs>
  );
}

// Navigate programmatically
import { router } from 'expo-router';
router.push('/product/42');
router.replace('/(tabs)/home');
```

**React Navigation (when more control needed):**
```tsx
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';

const Stack = createNativeStackNavigator<RootStackParamList>();

export default function App() {
  return (
    <NavigationContainer>
      <Stack.Navigator>
        <Stack.Screen name="Home" component={HomeScreen} />
        <Stack.Screen name="Detail" component={DetailScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
```

## Gotchas
- Expo Router requires `expo-router` plugin in `app.json` and `main` set to `expo-router/entry` in `package.json`
- React Navigation's `useNavigation()` throws if called outside `NavigationContainer`; wrap with a null check
- Nested navigators reset their own stack; use `navigation.getParent()` to navigate across boundaries
- Tab navigators keep screens mounted by default — use `unmountOnBlur` if state must reset
- Passing non-serializable objects as route params causes issues with state persistence and deep links
- `@react-navigation/native-stack` uses native primitives and is faster than the JS-based stack

## Related
- `react-native-deep-linking.md`
- `ios-universal-links.md`
- `android-deep-linking-intents.md`
