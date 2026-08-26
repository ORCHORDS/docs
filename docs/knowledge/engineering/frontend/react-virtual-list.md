# react-virtual-list

**Issue:** Rendering thousands of list items causes jank and high memory usage
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A feed with 10,000 items takes 3 seconds to render and scrolls at 15fps.

## Pattern / Solution
```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualList({ items }) {
  const parentRef = useRef(null);
  const virtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 50,
    overscan: 5,
  });
  return (
    <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map(item => (
          <div key={item.key} style={{ position: 'absolute', top: item.start, height: item.size }}>
            {items[item.index].name}
          </div>
        ))}
      </div>
    </div>
  );
}
```

## Gotchas
- Container must have a fixed height and overflow:auto/scroll
- Dynamic row heights require measureElement and a ResizeObserver
- react-window is lighter but less actively maintained

## Related
- `browser-intersection-observer.md`
- `browser-resize-observer.md`
