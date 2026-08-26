# react-native-bottom-sheet

**Issue:** Implementing performant, gesture-driven bottom sheets in React Native
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Modal-based bottom sheets from the RN core feel janky and don't support snap points or keyboard avoidance.

## Pattern / Solution
```sh
npm install @gorhom/bottom-sheet react-native-reanimated react-native-gesture-handler
```

```jsx
import BottomSheet, { BottomSheetView } from '@gorhom/bottom-sheet';
import { useRef, useMemo, useCallback } from 'react';

function App() {
  const sheetRef = useRef(null);
  const snapPoints = useMemo(() => ['25%', '50%', '90%'], []);

  const handleSheetChange = useCallback((index) => {
    console.log('snap point index:', index);
  }, []);

  return (
    <BottomSheet
      ref={sheetRef}
      index={1}              // initial snap point
      snapPoints={snapPoints}
      onChange={handleSheetChange}
      enablePanDownToClose
    >
      <BottomSheetView style={{ flex: 1, padding: 16 }}>
        <Text>Bottom Sheet Content</Text>
      </BottomSheetView>
    </BottomSheet>
  );
}

// Open / close programmatically
sheetRef.current?.expand();
sheetRef.current?.close();
```

## Gotchas
- Requires `react-native-reanimated` v2+ and `react-native-gesture-handler` — both must be initialized before use
- Wrap the root of the app in `<GestureHandlerRootView>` or gestures won't register
- `BottomSheetScrollView` must be used instead of `ScrollView` inside the sheet for nested scroll
- `enablePanDownToClose` with `index={-1}` initial state crashes on Android RN < 0.71

## Related
- `react-native-gesture-handler.md`
- `react-native-reanimated.md`
