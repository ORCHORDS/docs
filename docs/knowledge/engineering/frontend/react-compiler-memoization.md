# React Compiler: Automatic Memoization

## Symptom

Components re-render unnecessarily, causing jank. You reach for `useMemo`,
`useCallback`, and `React.memo` everywhere, but the memoization graph becomes
fragile — forget one dependency and you get a stale-value bug, or you over-
memoize and the overhead exceeds the savings. Code review turns into debates
about "does this need `useCallback`?"

With the React Compiler (stable in React 19.1+, 2026), the compiler analyzes
your components and hooks at build time and automatically inserts memoization
where the compiler can prove it is safe. You write plain, readable code; the
compiler handles the memo graph.

```jsx
// Before: manual and error-prone
const filtered = useMemo(() => items.filter(isActive), [items, isActive]);
const handleClick = useCallback(() => onSelect(id), [onSelect, id]);

// After: React Compiler handles it automatically
const filtered = items.filter(isActive);
const handleClick = () => onSelect(id);
```

## Gotchas

### The compiler is opt-in — you must enable it

The compiler does not run just because you upgraded React. You must configure
it in your bundler.

```js
// vite.config.js
import react from '@vitejs/plugin-react';

export default {
  plugins: [react({ babel: { plugins: [['babel-plugin-react-compiler']] } })],
};
```

```js
 // babel.config.js (for non-Vite)
 module.exports = {
   presets: ['@babel/preset-react'],
   plugins: [['babel-plugin-react-compiler']],
 };
```

### Not all code is compilable — the "rules of React" are enforced

The compiler will skip a component or hook if it violates the Rules of React
(no conditional hooks, no mutating props, no side effects in render). It logs
a warning and falls back to uncompiled output for that unit. You must fix the
violation; the compiler will not silently fix it for you.

```jsx
// BAD — compiler skips this hook entirely
function useBad() {
  if (cond) useEffect(() => {}, []); // conditional hook call
}

// BAD — mutating a prop, compiler bails out
function Item({ list }) {
  list.push('new'); // never mutate props
  return <ul>{list.map(/* ... */)}</ul>;
}
```

### `eslint-plugin-react-compiler` catches bailouts in CI

Install and enable the linter so CI fails when the compiler skips something
you intended it to optimize. A silent bailout means you ship un-memoized code
thinking it was optimized.

```bash
npm install -D eslint-plugin-react-compiler
```

```json
{
  "plugins": ["react-compiler"],
  "rules": { "react-compiler/react-compiler": "error" }
}
```

### Memoization is not free — the compiler can over-allocate

The compiler may insert memoization on cheap operations (simple string concat,
small array maps) where the memo bookkeeping costs more than recomputing.
Profile with React DevTools before assuming the compiler "fixed" your perf.

### Existing manual memoization becomes noise

After enabling the compiler, most hand-written `useMemo`/`useCallback` calls
are redundant. You can leave them (they still work) or remove them for
readability. Do NOT remove them before the compiler is enabled — that is a
perf regression.

### The compiler keys on component identity, not file path

Renaming a component or wrapping it in a higher-order component can change
what the compiler can prove. After refactors, re-run the linter to confirm
no new bailouts appeared.

## Practical migration

1. Enable `eslint-plugin-react-compiler` first, fix all reported violations.
2. Enable the babel plugin in dev only, verify the app behaves identically.
3. Enable in production. Monitor Core Web Vitals (INP especially).
4. Gradually strip manual memoization where the compiler now covers it.

## When you still need manual memoization

- Passing stable references to context providers consumed by many children.
- Interop with libraries that do shallow reference equality (MobX, some
  Redux selector patterns).
- Expensive computations whose inputs are stable but the compiler's analysis
  is too conservative to memoize them.
