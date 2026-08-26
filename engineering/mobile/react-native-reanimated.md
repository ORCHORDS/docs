# react-native-reanimated

**Issue:** Running complex, shared-value-driven animations entirely on the UI thread
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
`Animated` API cannot animate layout properties or run logic on the UI thread; Reanimated v3 worklets enable zero-lag animations.

## Pattern / Solution
```sh
npm install react-native-reanimated
npx pod-install
```

`babel.config.js`:
```js
module.exports = {
  presets: ['module:metro-react-native-babel-preset'],
  plugins: ['react-native-reanimated/plugin'], // must be last plugin
};
```

```jsx
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSpring,
  runOnJS,
} from 'react-native-reanimated';

function ScaleButton({ onPress }) {
  const scale = useSharedValue(1);

  const animStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return (
    <Animated.View style={[styles.btn, animStyle]}>
      <Pressable
        onPressIn={() => { scale.value = withSpring(0.92); }}
        onPressOut={() => {
          scale.value = withSpring(1);
          runOnJS(onPress)(); // call JS function from worklet
        }}
      />
    </Animated.View>
  );
}
```

## Gotchas
- The Babel plugin **must** be listed last in the `plugins` array or worklets are not transpiled
- Worklet functions cannot close over mutable JS variables — only shared values and constants
- `runOnJS` is needed to call any regular JS function (navigation, state updates) from a worklet
- Reanimated v3 requires React Native 0.71+ and Hermes engine

## Related
- `react-native-gesture-handler.md`
- `react-native-animated-api.md`
- `react-native-hermes-engine.md`
