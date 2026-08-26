# typescript-react-patterns

**Issue:** Common TypeScript patterns for typing React components and hooks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Props typed as any, event handlers with implicit any, and missing return types clutter the codebase.

## Pattern / Solution
```tsx
// Component props
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  loading?: boolean;
}

// Generic component
function List<T>({ items, renderItem }: {
  items: T[];
  renderItem: (item: T, index: number) => React.ReactNode;
}) {
  return <ul>{items.map((item, i) => <li key={i}>{renderItem(item, i)}</li>)}</ul>;
}

// Event types
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {};
const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {};

// Custom hook return type
function useToggle(initial = false): [boolean, () => void] {
  const [state, setState] = useState(initial);
  return [state, () => setState(s => !s)];
}
```

## Gotchas
- Prefer interface for public APIs; type for unions and computed types
- React.FC is deprecated; prefer explicit props with function declaration
- ComponentPropsWithoutRef vs ComponentPropsWithRef depending on ref needs

## Related
- `typescript-generic-components.md`
- `typescript-discriminated-unions-ui.md`
