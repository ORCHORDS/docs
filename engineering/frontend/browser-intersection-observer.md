# browser-intersection-observer

**Issue:** Scroll-based visibility detection with scroll event listeners is expensive
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Checking element visibility on every scroll event fires hundreds of times per second and causes jank.

## Pattern / Solution
```ts
// Lazy-load images
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      const img = entry.target as HTMLImageElement;
      img.src = img.dataset.src!;
      observer.unobserve(img);
    }
  });
}, { rootMargin: '200px', threshold: 0 });

document.querySelectorAll('img[data-src]').forEach(img => observer.observe(img));

// React hook
function useInView(ref: RefObject<Element>, options?: IntersectionObserverInit) {
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => setInView(e.isIntersecting), options);
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);
  return inView;
}
```

## Gotchas
- rootMargin is in CSS pixels relative to the viewport or root element
- threshold: 1.0 fires only when the element is fully visible
- Disconnect the observer to avoid memory leaks

## Related
- `html-lazy-loading-images.md`
- `react-virtual-list.md`
