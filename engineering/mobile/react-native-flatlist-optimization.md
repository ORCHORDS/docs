# react-native-flatlist-optimization

**Issue:** FlatList rendering large datasets causes jank, blank cells, and excessive memory use
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Scrolling through a list of 500+ items results in dropped frames and the "VirtualizedList: You have a large list" warning.

## Pattern / Solution
```jsx
<FlatList
  data={items}
  keyExtractor={(item) => item.id}
  renderItem={renderItem}
  // tune window sizes
  initialNumToRender={10}
  maxToRenderPerBatch={10}
  windowSize={5}           // default 21 — smaller = less memory
  removeClippedSubviews    // unmount off-screen items (Android)
  // stable layout avoids re-measure
  getItemLayout={(_, index) => ({
    length: ITEM_HEIGHT,
    offset: ITEM_HEIGHT * index,
    index,
  })}
/>

// Memoize the render function
const renderItem = useCallback(
  ({ item }) => <Row item={item} />,
  []
);

// Memoize Row itself
const Row = React.memo(({ item }) => <Text>{item.title}</Text>);
```

Use `FlashList` from Shopify for a drop-in replacement that is ~10× faster on large lists:
```sh
npx expo install @shopify/flash-list
```

## Gotchas
- `removeClippedSubviews` can cause blank flicker on iOS when combined with complex nested views
- Omitting `getItemLayout` forces a full measure pass for every scroll event
- Changing `data` reference on every render (e.g., inline array literals) causes full re-renders
- `keyExtractor` returning non-unique keys silently corrupts list state

## Related
- `react-native-performance-optimization.md`
- `react-native-animated-api.md`
