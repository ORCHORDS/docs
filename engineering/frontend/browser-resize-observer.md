# browser-resize-observer

**Issue:** Reacting to element size changes without polling or listening to window resize
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A chart needs to re-render when its container resizes, not just when the window resizes.

## Pattern / Solution
```ts
const observer = new ResizeObserver((entries) => {
  for (const entry of entries) {
    const { width, height } = entry.contentRect;
    resizeChart(width, height);
  }
});
observer.observe(chartContainer);
// Cleanup
observer.disconnect();

// React hook
function useElementSize(ref: RefObject<HTMLElement>) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!ref.current) return;
    const obs = new ResizeObserver(([entry]) => {
      setSize({ width: entry.contentRect.width, height: entry.contentRect.height });
    });
    obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return size;
}
```

## Gotchas
- ResizeObserver entries may fire loop-limit warnings if you resize the element inside the callback
- contentRect excludes padding and border (use borderBoxSize for those)
- Fires synchronously before paint; debounce if doing expensive work

## Related
- `browser-intersection-observer.md`
- `react-virtual-list.md`
