# react-form-handling-react-hook-form

**Issue:** Form state and validation with useState is verbose and error-prone
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A 10-field form requires 10 state variables, 10 onChange handlers, and manual validation logic.

## Pattern / Solution
```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  email: z.string().email(),
  age: z.number().min(18),
});

function Form() {
  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodResolver(schema),
  });
  return (
    <form onSubmit={handleSubmit(data => console.log(data))}>
      <input {...register('email')} />
      {errors.email && <span>{errors.email.message}</span>}
      <button type="submit">Submit</button>
    </form>
  );
}
```

## Gotchas
- register spreads ref, name, onChange, onBlur; do not override these
- Use Controller wrapper for custom controlled components like Select or DatePicker
- watch() re-renders on every keystroke; use getValues() in handlers instead

## Related
- `react-controlled-vs-uncontrolled.md`
- `html-form-validation.md`
