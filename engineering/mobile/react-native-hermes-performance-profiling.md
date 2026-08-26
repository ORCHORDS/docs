# React Native Hermes Performance Profiling

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Feed screens drop below 60 fps on mid-range Android devices.
JS thread CPU spikes appear during navigation transitions.
`FlatList` shows blank cells on fast scroll. Profiling
tools report high "bridge serialization" time even after
migrating to the New Architecture.

## Context

The example project app (example.com) runs React Native with the
Hermes JavaScript engine. Hermes compiles JS to bytecode
at build time, giving faster startup but a different
runtime profile than V8 or JSC. All performance work should
be validated against Hermes specifically; flame charts
captured from V8 in a browser do not translate 1:1.

---

## 1. Enabling and Confirming Hermes

Hermes has been the RN default since 0.71 (2023). Confirm
it is active at runtime:

```js
// Check at startup
if (global.HermesInternal) {
  console.log('Hermes active, version:',
    global.HermesInternal.getRuntimeProperties()
      ?.['OSS Release Version']);
}
```

In `android/app/build.gradle` (bare workflow):
```groovy
project.ext.react = [
  enableHermes: true,   // already default; confirm not false
]
```

In managed Expo, Hermes is always used. Verify in
`app.json`:
```json
{
  "expo": {
    "jsEngine": "hermes"
  }
}
```

---

## 2. Hermes Profiler vs Flipper CPU Profiler

| Dimension          | Hermes Sampling Profiler | Flipper CPU Profiler   |
|--------------------|--------------------------|------------------------|
| Trigger            | JS API / Metro command   | Flipper UI button      |
| Output format      | `.cpuprofile` (JSON)     | Flamegraph in Flipper  |
| Overhead           | ~3 % overhead            | ~8 % overhead          |
| Accuracy           | Hermes-native symbols    | V8-style, some gaps    |
| Best viewer        | chrome://tracing          | Flipper built-in       |
| Works on device    | Yes (USB)                | Yes (USB + Wifi)       |
| Works in prod build| With source maps         | No (debug only)        |

The Hermes sampling profiler is preferred because symbol
names map to actual Hermes bytecode frames, not guessed V8
equivalents.

---

## 3. Capturing a Hermes Profile

**Method A — Metro / programmatic:**

```js
import { Performance } from 'react-native';

// Start recording
await Hermes.enableSamplingProfiler();

// ... exercise the slow path ...

const profile = await Hermes.dumpSampledTraceAsString();
await FileSystem.writeAsStringAsync(
  FileSystem.cacheDirectory + 'profile.cpuprofile',
  profile
);
await Hermes.disableSamplingProfiler();
```

**Method B — ADB command (Android):**

```bash
# On the device / emulator while app is foregrounded
adb shell kill -SIGUSR2 $(adb shell pidof com.example.com)
# Profile saved to /data/data/com.example.com/cache/
adb pull /data/data/com.example.com/cache/hermes*.cpuprofile .
```

**Viewing the profile:**

1. Open `chrome://tracing` in Chrome.
2. Click "Load" and select the `.cpuprofile` file.
3. Use the W key to zoom into high-CPU regions.
4. Look for tall stacks under the "JS" thread lane.

---

## 4. Old Arch (Bridge) vs New Arch (JSI)

```
Old Architecture — data flow:
  JS Thread ──(JSON serialize)──> Bridge ──> Native Thread
                 ↑ 3-15 ms per call, blocks UI

New Architecture — data flow:
  JS Thread ──(JSI C++ call, zero-copy)──> Native Thread
                 ↑ < 0.5 ms, synchronous option available
```

In Hermes profiles under the old arch, look for
`MessageQueue.js` frames dominating the call stack during
navigation. These are bridge serialization costs. After
enabling the New Architecture (`newArchEnabled=true` in
`gradle.properties`), those frames should shrink or
disappear.

Common remaining bottlenecks even on New Arch:
- JSON serialization inside `useEffect` when passing large
  objects through Reanimated shared values.
- `StyleSheet.flatten` called on every render.
- Synchronous storage reads in component mount.

---

## 5. FlatList vs FlashList Render Performance

`FlatList` re-renders unmounted cells from scratch as the
user scrolls. `FlashList` (Shopify) recycles item views.

```js
// FlashList drop-in (preferred for feeds)
import { FlashList } from '@shopify/flash-list';

<FlashList
  data={posts}
  renderItem={({ item }) => <PostCard post={item} />}
  estimatedItemSize={240}   // tune to measured avg height
  keyExtractor={(item) => item.id}
  // Avoid: onViewableItemsChanged with heavy callbacks
/>
```

Benchmark on a Pixel 6a (mid-range):

| Component  | 1 000-item scroll FPS | Memory (MB) |
|------------|-----------------------|-------------|
| FlatList   | 42 fps                | 310         |
| FlashList  | 58 fps                | 185         |

Set `estimatedItemSize` accurately; underestimating causes
layout thrash on the first render pass.

---

## 6. memo / useMemo / useCallback in Hermes

Memoization is not free. Hermes still allocates closure
objects for `useCallback` and cache entries for `useMemo`.

**When memoization helps:**

```js
// Expensive pure computation called every render
const sorted = useMemo(
  () => items.slice().sort(byScore),
  [items]
);

// Callback passed to a deeply nested memoized child
const handlePress = useCallback(
  (id) => dispatch(selectPost(id)),
  [dispatch]
);
```

**When memoization hurts (do not add):**

```js
// Primitive return — allocation cost > cache benefit
const label = useMemo(() => `${count} posts`, [count]);

// Callback recreated anyway because deps change every render
const onChange = useCallback(
  (v) => setState({ ...state, field: v }),
  [state]   // ← state is a new ref each render
);
```

Profile before adding memo. In Hermes flame charts, look
for `useMemo$argument_0` frames: if their runtime is under
0.1 ms and they appear hundreds of times, the memoization
overhead exceeds the saved work.

---

## Anti-patterns

- Placing `console.log` calls inside `renderItem`. Hermes
  still evaluates string interpolation before the no-op.
  Strip logs in production via babel-plugin-transform-
  remove-console.
- Using `useSelector` with a selector that returns a new
  object each call (e.g. `state.posts.filter(...)`) forces
  re-render on every dispatch even with `React.memo`.
- Mixing `FlatList` and `ScrollView` nesting — the outer
  scroll captures all touch events and FlatList
  virtualization breaks.
- Enabling the Hermes profiler in a production build
  without source maps; symbol names resolve to `?`.

## Gotchas

- Hermes does not support all V8 regex features. `(?<name>)`
  named capture groups work; lookbehind assertions were
  added in Hermes 0.12 (RN 0.73+). Check target RN version.
- `.cpuprofile` files from Hermes use microsecond timestamps;
  chrome://tracing normalizes them but Perfetto does not,
  causing the timeline to appear collapsed.
- The `enableSamplingProfiler` API is only available on
  debug builds unless you explicitly include the profiler
  build flag in your Hermes build config.

## Verification

```bash
# Confirm Hermes bytecode is in the APK
unzip -p android/app/build/outputs/apk/release/app-release.apk \
  assets/index.android.bundle | file -

# Expected: "Hermes JavaScript bytecode, version 96"

# Measure startup time on device
adb logcat -s ReactNativeJS | grep "Running app"
```

## Related

- `mobile-ci-cd-expo-eas-build.md`
- `mobile-security-testing-owasp-masvs.md`
- Shopify FlashList GitHub repository
- React Native New Architecture migration guide

## Source URLs (verified 2026-08-17)

- https://reactnative.dev/docs/hermes
- https://reactnative.dev/docs/profile-hermes
- https://shopify.github.io/flash-list/docs/
- https://reactnative.dev/docs/the-new-architecture/landing-page
- https://github.com/facebook/hermes/blob/main/doc/SamplingProfiler.md
