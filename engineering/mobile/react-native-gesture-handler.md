# react-native-gesture-handler

**Issue:** Native-driven gesture recognition that avoids JS thread lag in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The built-in `PanResponder` runs on the JS thread and causes gesture lag during heavy renders; `react-native-gesture-handler` processes gestures natively.

## Pattern / Solution
```sh
npm install react-native-gesture-handler
npx pod-install
```

Wrap root in `index.js`:
```js
import 'react-native-gesture-handler'; // must be first import
```

And in the component tree:
```jsx
import { GestureHandlerRootView } from 'react-native-gesture-handler';

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <Navigation />
    </GestureHandlerRootView>
  );
}
```

Gesture API (v2):
```jsx
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { useSharedValue, useAnimatedStyle, withSpring } from 'react-native-reanimated';

function DraggableBox() {
  const offsetX = useSharedValue(0);
  const offsetY = useSharedValue(0);

  const panGesture = Gesture.Pan()
    .onUpdate((e) => {
      offsetX.value = e.translationX;
      offsetY.value = e.translationY;
    })
    .onEnd(() => {
      offsetX.value = withSpring(0);
      offsetY.value = withSpring(0);
    });

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: offsetX.value }, { translateY: offsetY.value }],
  }));

  return (
    <GestureDetector gesture={panGesture}>
      <Animated.View style={[styles.box, animStyle]} />
    </GestureDetector>
  );
}
```

## Gotchas
- Import must be the very first line in `index.js` to correctly patch the native bridge
- V1 API (`PanGestureHandler`, `TapGestureHandler`) still works but is deprecated
- On Android, `<GestureHandlerRootView>` must span the full screen or touches outside it fail
- Navigation libraries (React Navigation) require RNGF; ensure versions are compatible

## Related
- `react-native-reanimated.md`
- `react-native-bottom-sheet.md`
- `react-native-animated-api.md`
