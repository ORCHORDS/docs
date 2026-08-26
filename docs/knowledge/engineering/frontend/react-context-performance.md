# react-context-performance

**Issue:** Context value changes re-render all consumers even when their slice is unchanged
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A global context holding auth state and UI preferences re-renders notification badges every time the theme changes.

## Pattern / Solution
```tsx
// Split contexts by update frequency
const AuthContext = createContext(null);
const ThemeContext = createContext(null);

// Memoize the value object
function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const value = useMemo(() => ({ user, setUser }), [user]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
```

## Gotchas
- Object literals as context value recreate on every render
- Context is not a replacement for a state manager in large apps
- use(Context) in React 19 still triggers re-renders on any value change

## Related
- `react-state-management-zustand.md`
- `react-state-management-jotai.md`
