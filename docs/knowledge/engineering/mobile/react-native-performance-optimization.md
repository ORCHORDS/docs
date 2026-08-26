# react-native-performance-optimization

**Issue:** Identifying and fixing performance bottlenecks in React Native apps
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Common symptoms: dropped frames during scroll, slow screen transitions, high JS thread CPU, large memory footprint. Root causes include re-renders, heavy JS work on the main thread, and unoptimized images.

## Pattern / Solution
**Prevent unnecessary re-renders:**
```tsx
// Memoize expensive components
const HeavyCard = React.memo(({ item }: { item: Item }) => <Card data={item} />,
  (prev, next) => prev.item.id === next.item.id
);

// Stable callbacks
const handlePress = useCallback(() => navigate(item.id), [item.id]);

// Derived state with useMemo
const sorted = useMemo(() => [...data].sort(comparator), [data]);
```

**FlatList optimizations:**
```tsx
<FlatList
  data={items}
  keyExtractor={item => item.id}
  renderItem={renderItem}
  getItemLayout={(_, index) => ({ length: ITEM_HEIGHT, offset: ITEM_HEIGHT * index, index })}
  maxToRenderPerBatch={10}
  windowSize={5}
  removeClippedSubviews={true}
  initialNumToRender={8}
/>
```

**Move heavy work off JS thread:**
```ts
// Worklets with Reanimated (runs on UI thread)
import { runOnJS, useAnimatedScrollHandler } from 'react-native-reanimated';

// Offload CPU work to a thread pool
import { runAsync } from 'react-native-quick-base64'; // example of JSI module
```

**Image optimization:**
```tsx
import { Image } from 'expo-image'; // blurhash placeholder, fast caching

<Image
  source={{ uri: url }}
  placeholder={blurhash}
  contentFit="cover"
  transition={200}
  cachePolicy="memory-disk"
/>
```

**Profile with Flipper / Hermes sampling profiler:**
```bash
# Enable in Metro
HERMES_ENABLE_PROFILER=1 npx expo start
# Then record in Flipper → Hermes Debugger → Profiler
```

## Gotchas
- `console.log` in production is surprisingly expensive; strip with `babel-plugin-transform-remove-console`
- `StyleSheet.create` is a no-op performance-wise in the new architecture; the benefit was always about validation
- `InteractionManager.runAfterInteractions` defers heavy init until after animations settle
- Avoid anonymous functions in JSX (`onPress={() => fn()}`) inside lists — they create new references on every render
- `removeClippedSubviews` can cause visual glitches if items have overflow content; test carefully

## Related
- `react-native-hermes-engine.md`
- `react-native-new-architecture.md`
- `mobile-performance-profiling.md`
- `mobile-image-caching-patterns.md`
