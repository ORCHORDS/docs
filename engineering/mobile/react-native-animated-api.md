# react-native-animated-api

**Issue:** Using the built-in Animated API for smooth, performant animations in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Animations running on the JS thread drop frames and stutter, especially during heavy JS work or list scrolling.

## Pattern / Solution
Use `useNativeDriver: true` for transform/opacity animations to run entirely on the UI thread.

```js
import { Animated, useRef, useEffect } from 'react-native';

function FadeIn({ children }) {
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: 1,
      duration: 300,
      useNativeDriver: true, // offloads to UI thread
    }).start();
  }, []);

  return <Animated.View style={{ opacity }}>{children}</Animated.View>;
}

// Sequence / parallel composition
Animated.sequence([
  Animated.delay(100),
  Animated.spring(scale, { toValue: 1.2, useNativeDriver: true }),
  Animated.spring(scale, { toValue: 1, useNativeDriver: true }),
]).start();

// Interpolation for derived values
const rotate = opacity.interpolate({
  inputRange: [0, 1],
  outputRange: ['0deg', '360deg'],
});
```

## Gotchas
- `useNativeDriver: true` does **not** support `width`, `height`, or `margin` — only transform and opacity
- Calling `.setValue()` during an ongoing animation causes a hard reset, not a smooth transition
- `Animated.event` with `useNativeDriver` requires the gesture handler to be native too
- Looping animations must call `.start()` inside the completion callback, not via `Animated.loop` when using native driver on older RN

## Related
- `react-native-reanimated.md`
- `react-native-gesture-handler.md`
- `react-native-performance-optimization.md`
