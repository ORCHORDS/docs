# react-compound-components

**Issue:** Highly configurable components become prop-heavy and hard to compose
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A Tabs component with 15 props for header styles, content, icons, and callbacks is hard to extend.

## Pattern / Solution
```tsx
const TabsContext = createContext(null);

function Tabs({ children, defaultValue }) {
  const [active, setActive] = useState(defaultValue);
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div>{children}</div>
    </TabsContext.Provider>
  );
}

function Tab({ value, children }) {
  const { active, setActive } = useContext(TabsContext);
  return <button aria-selected={active === value} onClick={() => setActive(value)}>{children}</button>;
}

Tabs.Tab = Tab;

// Usage
<Tabs defaultValue="a"><Tabs.Tab value="a">First</Tabs.Tab></Tabs>
```

## Gotchas
- Consumers must nest components within the correct Provider tree
- Export compound components as named exports for tree-shaking
- React.Children iteration is fragile; prefer context

## Related
- `react-render-props-pattern.md`
- `react-context-performance.md`
