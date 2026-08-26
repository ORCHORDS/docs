# react-native-dark-mode

**Issue:** Supporting system-level dark mode in React Native apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Apps that ignore the system color scheme appear outdated and cause eye strain in dark environments.

## Pattern / Solution
```tsx
import { useColorScheme } from 'react-native';

// Hook-based detection
function ThemedView() {
  const scheme = useColorScheme(); // 'light' | 'dark' | null
  const isDark = scheme === 'dark';

  return (
    <View style={{ backgroundColor: isDark ? '#121212' : '#ffffff' }}>
      <Text style={{ color: isDark ? '#e0e0e0' : '#212121' }}>Hello</Text>
    </View>
  );
}

// Design-token approach (recommended)
const Colors = {
  light: { background: '#ffffff', text: '#212121', primary: '#6200ee' },
  dark:  { background: '#121212', text: '#e0e0e0', primary: '#bb86fc' },
};

function useTheme() {
  const scheme = useColorScheme() ?? 'light';
  return Colors[scheme];
}

// With React Navigation
import { DarkTheme, DefaultTheme, NavigationContainer } from '@react-navigation/native';

<NavigationContainer theme={isDark ? DarkTheme : DefaultTheme}>
  <Stack.Navigator />
</NavigationContainer>
```

## Gotchas
- `useColorScheme()` returns `null` on first render in some RN versions — always provide a fallback
- Native modals and system UI (status bar, keyboard) must be styled separately via `StatusBar` component
- Images and icons may need dark-mode variants; use `Image` with a conditional `source` prop
- Expo Router exposes `useColorScheme` from `expo-router` — use that instead of the RN one in Expo apps

## Related
- `react-native-splash-screen.md`
- `react-native-accessibility.md`
