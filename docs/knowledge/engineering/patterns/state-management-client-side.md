# state-management-client-side

**Issue:** Client-side state — useState, Zustand, Redux, Jotai
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your React app has 50 components. State is shared via
props (passing it down 5 levels). A change at the top
re-renders 20 components. The app is slow. The team adds
a state management library. Now the state lives in
"the store" but nobody knows where the source of truth
is.

## Root cause
**State management is hard.** Without a clear pattern, state
is scattered, props are passed deep, and re-renders are
wasteful.

**Source:** React docs on state:
https://react.dev/learn/managing-state

## The "state category" framework

React's docs identify 4 categories:

1. **Local state:** Used by one component. (e.g. form input)
2. **Shared state:** Used by a few components in the same
   tree. (e.g. modal open/close)
3. **Global state:** Used by many components across the
   app. (e.g. user info, theme)
4. **Server state:** Data from the server. (e.g. user list,
   posts)

Each category has a different solution.

## The 4 patterns

### 1. Local state: useState / useReducer
```ts
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```

✅ Simple
✅ Fast
❌ Not shared

### 2. Shared state: Context + useState
```ts
const ThemeContext = createContext('light');

function App() {
  const [theme, setTheme] = useState('light');
  return (
    <ThemeContext.Provider value={[theme, setTheme]}>
      <Header />
      <Main />
    </ThemeContext.Provider>
  );
}

function Header() {
  const [theme, setTheme] = useContext(ThemeContext);
  return <button onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}>...</button>;
}
```

✅ Simple
✅ Shared
❌ Re-renders all consumers on change
❌ Not great for high-frequency updates

### 3. Global state: Zustand / Redux
```ts
import { create } from 'zustand';

const useStore = create((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  theme: 'light',
  setTheme: (theme) => set({ theme }),
}));

function UserMenu() {
  const user = useStore((s) => s.user);
  return <div>{user?.displayName}</div>;
}
```

✅ Scoped updates (only components using `user` re-render)
✅ Devtools support
✅ Easy to test
❌ More setup than useState

### 4. Server state: React Query / SWR
```ts
import { useQuery } from '@tanstack/react-query';

function UserList() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['users'],
    queryFn: () => fetch('/api/users').then(r => r.json()),
  });
  if (isLoading) return <Spinner />;
  if (error) return <Error />;
  return <List items={data} />;
}
```

✅ Caching, dedup, refetch
✅ Optimistic updates
✅ Background refresh
❌ More setup
❌ Overkill for trivial data

## The "decision matrix"

| State | Tool |
|---|---|
| 1 component | useState |
| Form state | React Hook Form / Formik |
| Modal open/close | Local state (lifted if needed) |
| User info, theme | Zustand / Context |
| API data | React Query / SWR |
| Complex shared state | Redux Toolkit |

## The "anti-patterns" of state management

### 1. Everything in Redux
```ts
// ❌ Overkill
const store = {
  modalOpen: false,
  isLoading: true,
  formInput: '',
  // ... 100 more fields
};
```

Redux is for global state. Local state should be useState.

### 2. Everything in Context
```ts
// ❌ Context for high-frequency state causes re-renders
<ThemeContext.Provider value={{ theme, setTheme, count, increment, ... }}>
  <App />
</ThemeContext.Provider>
```

Context triggers re-renders for all consumers. For high-
frequency updates, use a state library (Zustand, Jotai).

### 3. Fetching in useEffect
```ts
// ❌ Common mistake
function UserList() {
  const [users, setUsers] = useState([]);
  useEffect(() => {
    fetch('/api/users').then(r => r.json()).then(setUsers);
  }, []);
  return <List items={users} />;
}
```

No caching, no dedup, no error handling. Use React Query.

### 4. Duplicating server state
```ts
// ❌ State that mirrors server state
const [serverData, setServerData] = useState(null);
// ... fetch and setServerData
// Now serverData is the "source of truth" but the server
// has the real source. They will diverge.
```

The server is the source of truth. Use React Query to
mirror it; don't duplicate.

## The "Zustand" pattern

For most apps, **Zustand** is the right global state tool:
```ts
import { create } from 'zustand';

interface AppState {
  user: User | null;
  setUser: (user: User | null) => void;
  theme: 'light' | 'dark';
  setTheme: (theme: 'light' | 'dark') => void;
}

const useApp = create<AppState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  theme: 'light',
  setTheme: (theme) => set({ theme }),
}));

// Usage
function UserMenu() {
  const user = useApp((s) => s.user);  // Only re-renders on user change
  return <div>{user?.displayName}</div>;
}
```

Zustand is 3kb, has TypeScript support, and is fast.

## The "React Query" pattern

For server state:
```ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: () => fetch('/api/users').then(r => r.json()),
    staleTime: 60_000,  // Don't refetch for 1 minute
  });
}

function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: UserInput) =>
      fetch('/api/users', { method: 'POST', body: JSON.stringify(input) }).then(r => r.json()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });  // Refetch
    },
  });
}
```

The mutation automatically invalidates the list query; the
list re-fetches.

## The "performance" tips

1. **Memoize expensive components:** `React.memo`
2. **Use selectors for global state:** Only re-render on the
   specific state change
3. **Avoid prop drilling:** Use Context or Zustand
4. **Lazy load routes:** `React.lazy` for code splitting
5. **Virtualize long lists:** `react-window` for 1000+ items

## The "SSR-friendly" state

For SSR (Next.js, Remix, etc.), state must be serializable:
- ✅ useState, useReducer, Zustand (with persist middleware)
- ❌ Functions, classes, symbols

For server state, React Query works on both server and client.

## Verification
- **Test:** `test/state.test.ts > components render the
  expected state` — passes
- **Live:** Page performance (Time to Interactive, TTI) is
  monitored
- **Audit:** Annual review of state architecture

## Gotchas
- **Zustand / Redux are for global state, not local.**
  Don't put form input in Zustand; use useState.
- **React Query is for server state, not local.** Don't
  put "modal open" in React Query.
- **The "Context for everything" pattern re-renders a lot.**
  Use a state library for high-frequency updates.
- **State management libraries add complexity.** Use them
  when needed; don't preemptively add Redux to a simple
  app.
- **The "store" is not always the answer.** Sometimes
  props + lifting state is the right pattern. Don't add
  a state library for 3 components.

## Related
- `frontend-bundle-optimization.md` (smaller bundles = faster
  state updates)
- `accessibility-wcag.md` (state changes need a11y support)
- `test-pyramid.md` (testing state)
- React Query: https://tanstack.com/query/latest
- Zustand: https://github.com/pmndrs/zustand
- React state: https://react.dev/learn/managing-state
