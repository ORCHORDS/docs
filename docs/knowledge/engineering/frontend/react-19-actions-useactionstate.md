# React 19 Actions and useActionState

React 19 introduces powerful new hooks for handling form actions and server interactions. These tools provide better performance, improved user experience, and cleaner code compared to previous approaches.

## Cover: useActionState, useFormStatus, useOptimistic, server actions, migration from useMutation

The new action system in React 19 includes `useActionState`, `useFormStatus`, and `useOptimistic` hooks that work together with server actions. These hooks simplify form handling and provide better control over optimistic updates and loading states.

## Symptom

Before React 19, developers relied on custom hooks or libraries like React Query for managing form state and server interactions. This often resulted in complex code with multiple state management patterns and manual loading state handling.

## Gotchas

- Server actions require a new component structure using the `use server` directive
- `useActionState` returns `[state, dispatch]` which must be handled carefully
- Optimistic updates need to be properly reverted on server errors
- Migration from `useMutation` requires refactoring existing form handling logic

## Practical Implementation

```jsx
// Server action component
'use client'

import { useActionState, useFormStatus } from 'react-dom'
import { submitForm } from './actions'

function FormComponent() {
  const [state, action, isPending] = useActionState(submitForm, null)

  return (
    <form action={action}>
      <input name="name" />
      <SubmitButton />
    </form>
  )
}

function SubmitButton() {
  const { pending } = useFormStatus()

  return (
    <button type="submit" disabled={pending}>
      {pending ? 'Submitting...' : 'Submit'}
    </button>
  )
}
```

## Migration from useMutation

Migrating from `useMutation` to React 19 actions involves:
1. Creating server actions instead of client-side mutation functions
2. Replacing manual loading state management with `useFormStatus`
3. Using `useActionState` for handling form state and errors
4. Leveraging optimistic updates through `useOptimistic`

## Key Benefits

- Built-in server integration eliminates need for external libraries
- Optimistic UI updates work seamlessly with server actions
- Better error handling and state management
- Reduced boilerplate code for common form patterns
- Improved performance through automatic batching
