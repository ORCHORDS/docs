# react-hooks-rules

**Issue:** Hooks called conditionally or inside loops cause state corruption
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
React throws "Rendered more hooks than during the previous render" or state gets assigned to wrong component instance.

## Pattern / Solution
```tsx
// BAD
function Component({ show }) {
  if (show) {
    const [val, setVal] = useState(0);
  }
}
// GOOD
function Component({ show }) {
  const [val, setVal] = useState(0);
  if (!show) return null;
}
```
ESLint plugin: `eslint-plugin-react-hooks` enforces the rules automatically.

## Gotchas
- Custom hooks must also follow the rules
- Hooks inside callbacks or event handlers are also forbidden
- The order must be identical across renders

## Related
- `react-useeffect-cleanup.md`
- `react-usememo-when-to-use.md`
