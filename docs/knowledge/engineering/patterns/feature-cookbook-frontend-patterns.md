# feature-cookbook-frontend-patterns

**Issue:** Frontend patterns — state, fetch, error
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a React app. The state is in 10 places. The
fetch logic is duplicated. The error handling is
inconsistent. You wish you had a structure.

## Root cause
**Without patterns, frontend code drifts.** Use
established patterns.

**Source:** React docs.

## The "data fetching" pattern

For data fetching, use a query library:
- **TanStack Query (React Query):** Caching, retries
- **SWR:** Simple, popular
- **RTK Query:** Redux + fetch

```tsx
import { useQuery } from '@tanstack/react-query';

function UserProfile({ userId }: { userId: string }) {
  const { data, error, isLoading } = useQuery({
    queryKey: ['user', userId],
    queryFn: () => fetch(`/api/users/${userId}`).then(r => r.json()),
  });

  if (isLoading) return <Spinner />;
  if (error) return <Error error={error} />;
  return <div>{data.displayName}</div>;
}
```

The fetch is declarative.

**Source:** TanStack Query:
https://tanstack.com/query

## The "mutation" pattern

For mutations:
```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';

function UpdateUser() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (data: UpdateUserInput) => fetch('/api/users/me', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user', 'me'] });
    },
  });

  return (
    <form onSubmit={mutation.mutate}>
      <input name="displayName" />
      <button type="submit" disabled={mutation.isPending}>
        {mutation.isPending ? 'Saving...' : 'Save'}
      </button>
    </form>
  );
}
```

The mutation is clean.

## The "form" pattern

For forms, use a form library:
- **React Hook Form:** Popular
- **Formik:** Mature
- **Final Form:** Mature

```tsx
import { useForm } from 'react-hook-form';

function SignupForm() {
  const { register, handleSubmit, formState: { errors } } = useForm<SignupInput>();

  const onSubmit = async (data: SignupInput) => {
    await fetch('/api/users', { method: 'POST', body: JSON.stringify(data) });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('email', { required: true })} />
      {errors.email && <span>Email is required</span>}
      <input {...register('password', { required: true, minLength: 8 })} />
      {errors.password && <span>Password must be at least 8 characters</span>}
      <button type="submit">Sign up</button>
    </form>
  );
}
```

The form is declarative.

**Source:** React Hook Form:
https://react-hook-form.com/

## The "error boundary" pattern

For error boundaries:
```tsx
import { ErrorBoundary } from 'react-error-boundary';

function ErrorFallback({ error }: { error: Error }) {
  return (
    <div>
      <h1>Something went wrong</h1>
      <pre>{error.message}</pre>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <Router />
    </ErrorBoundary>
  );
}
```

The error is caught.

**Source:** React Error Boundaries:
https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary

## The "loading state" pattern

For loading state, use Suspense:
```tsx
import { Suspense } from 'react';

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <UserProfile userId="u_1" />
    </Suspense>
  );
}
```

The loading is declarative.

## The "state management" pattern

For state management, choose by complexity:
- **Local:** `useState` + `useReducer`
- **Shared:** Context
- **Server:** TanStack Query
- **Complex:** Zustand, Redux, Jotai

For most apps, **useState + Context + TanStack Query** is
enough.

```tsx
// Local state
function Counter() {
  const [count, setCount] = useState(0);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}

// Context for shared state
const ThemeContext = createContext<'light' | 'dark'>('light');

function App() {
  return (
    <ThemeContext.Provider value="dark">
      <Router />
    </ThemeContext.Provider>
  );
}
```

The state is scoped.

## The "optimistic update" pattern

For optimistic updates:
```tsx
const mutation = useMutation({
  mutationFn: (data) => fetch('/api/like', { method: 'POST', body: JSON.stringify(data) }),
  onMutate: async (data) => {
    await queryClient.cancelQueries({ queryKey: ['post', data.postId] });
    const previous = queryClient.getQueryData(['post', data.postId]);
    queryClient.setQueryData(['post', data.postId], (old: any) => ({
      ...old,
      liked: true,
    }));
    return { previous };
  },
  onError: (err, data, context) => {
    queryClient.setQueryData(['post', data.postId], context!.previous);
  },
});
```

The UI updates immediately.

## The "infinite scroll" pattern

For infinite scroll:
```tsx
import { useInfiniteQuery } from '@tanstack/react-query';

function PostsList() {
  const { data, fetchNextPage, hasNextPage } = useInfiniteQuery({
    queryKey: ['posts'],
    queryFn: ({ pageParam }) => fetch(`/api/posts?cursor=${pageParam}`).then(r => r.json()),
    initialPageParam: '',
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });

  return (
    <div>
      {data?.pages.map(page => page.data.map(post => <Post key={post.id} post={post} />))}
      {hasNextPage && <button onClick={() => fetchNextPage()}>Load more</button>}
    </div>
  );
}
```

The scroll is infinite.

## The "accessibility" pattern

For a11y, ARIA + semantic HTML:
```tsx
function Modal({ isOpen, onClose, children }: ModalProps) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <h2 id="modal-title">Modal Title</h2>
      {children}
      <button onClick={onClose} aria-label="Close modal">X</button>
    </div>
  );
}
```

The modal is accessible.

**Source:** WAI-ARIA:
https://www.w3.org/WAI/ARIA/

## The "frontend anti-pattern" anti-patterns

### 1. No data fetching library
- **Issue:** Manual fetch + cache everywhere
- **Fix:** Use TanStack Query

### 2. Global state for everything
- **Issue:** Prop drilling + re-renders
- **Fix:** Use local state + Context

### 3. No error boundary
- **Issue:** One bug breaks the whole app
- **Fix:** Error boundaries

### 4. No loading state
- **Issue:** UI flickers
- **Fix:** Skeleton + Suspense

### 5. No accessibility
- **Issue:** Screen readers can't navigate
- **Fix:** ARIA + semantic HTML

## Verification
- **Test:** Renders correctly
- **Test:** State changes correctly
- **Test:** Errors are caught
- **Test:** Accessibility (a11y)
- **Live:** Lighthouse score
- **Audit:** Quarterly review

## Gotchas
- **The "global state for everything" anti-pattern.**
  Local + context.
- **The "no error boundary" anti-pattern.** Use one.
- **The "no a11y" anti-pattern.** ARIA + semantic.

## Related
- `feature-cookbook-frontend.md`
- `feature-cookbook-testing-frontend.md`
- `accessibility-wcag.md`
- `accessibility-components.md`
- React: https://react.dev/
- TanStack Query: https://tanstack.com/query
- React Hook Form: https://react-hook-form.com/
- WAI-ARIA: https://www.w3.org/WAI/ARIA/
