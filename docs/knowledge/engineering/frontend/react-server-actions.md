# react-server-actions

**Issue:** Form submissions require manual API route boilerplate in Next.js
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Every form needs a route handler, fetch call, and error handling wiring duplicated across the app.

## Pattern / Solution
```tsx
// app/actions.ts
'use server';
import { revalidatePath } from 'next/cache';
export async function createPost(formData: FormData) {
  const title = formData.get('title') as string;
  await db.insert({ title });
  revalidatePath('/posts');
}

// app/new-post/page.tsx
import { createPost } from '../actions';
export default function Page() {
  return (
    <form action={createPost}>
      <input name="title" />
      <button type="submit">Create</button>
    </form>
  );
}
```

## Gotchas
- Validate formData with zod before processing; never trust client input
- useFormStatus for pending state; useActionState for return value
- Server Actions run on the server; never log secrets to the client

## Related
- `react-server-components.md`
- `react-form-handling-react-hook-form.md`
