# react-ref-forwarding

**Issue:** Parent components cannot access DOM nodes of child components
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A form library needs to call .focus() on a custom Input component but the ref attaches to the wrapper div.

## Pattern / Solution
```tsx
// React 19: ref is a plain prop
function Input({ ref, ...props }) {
  return <input ref={ref} {...props} />;
}

// React 18: forwardRef
const Input = forwardRef<HTMLInputElement, InputProps>(({ label, ...props }, ref) => (
  <label>{label}<input ref={ref} {...props} /></label>
));

// Expose imperative handle
const FancyInput = forwardRef((props, ref) => {
  const inputRef = useRef(null);
  useImperativeHandle(ref, () => ({
    focus: () => inputRef.current?.focus(),
  }));
  return <input ref={inputRef} {...props} />;
});
```

## Gotchas
- React 19 removes the need for forwardRef; ref is a plain prop
- useImperativeHandle should expose a minimal API, not the raw DOM node
- Refs are not reactive; changes do not trigger re-renders

## Related
- `react-portal-patterns.md`
- `react-compound-components.md`
