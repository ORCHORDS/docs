# Form Validation with Zod and a Workers Validation Endpoint

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

You have a React form that submits to a Cloudflare Workers API. You want the same validation rules to run both client-side (for instant feedback) and server-side (for security). You also need structured field-level error messages that map directly to React Hook Form's `setError` API without any manual translation layer. Maintaining two separate validation schemas (one in the browser, one in the Worker) drifts within weeks and creates exploitable gaps.

The solution: define a single Zod schema, share it between the client bundle and the Worker via a monorepo package, run it on the client for UX, and re-run it in the Worker for trust.

---

## Context

Zod is a TypeScript-first schema declaration and parsing library. It produces fully-typed parse results and structures errors as a flat `ZodError.flatten()` map that matches React Hook Form's `FieldErrors` shape. Cloudflare Workers run the V8 JS engine—Zod works without modification. The patterns below assume:

- A Turborepo (or pnpm workspace) with a shared `packages/schemas` package.
- `react-hook-form` + `@hookform/resolvers/zod` on the client.
- A Cloudflare Pages Function (`functions/api/`) as the endpoint.

---

## 1. Shared Schema Package

```typescript
// packages/schemas/src/contact.ts
import { z } from 'zod';

export const ContactSchema = z.object({
  name: z
    .string()
    .min(2, 'Name must be at least 2 characters')
    .max(100, 'Name cannot exceed 100 characters')
    .regex(/^[\p{L}\s'-]+$/u, 'Name contains invalid characters'),

  email: z
    .string()
    .email('Enter a valid email address')
    .max(254, 'Email address is too long'),

  message: z
    .string()
    .min(10, 'Message must be at least 10 characters')
    .max(2000, 'Message cannot exceed 2000 characters')
    .trim(),

  agreeToTerms: z
    .boolean()
    .refine((val) => val === true, { message: 'You must agree to the terms' }),
});

export type ContactFormData = z.infer<typeof ContactSchema>;

// Serialisable subset of ZodError for the API response
export interface ValidationErrorResponse {
  ok: false;
  errors: {
    fieldErrors: Partial<Record<keyof ContactFormData, string[]>>;
    formErrors: string[];
  };
}

export interface SuccessResponse {
  ok: true;
  id: string;
}

export type ContactApiResponse = ValidationErrorResponse | SuccessResponse;
```

```json
// packages/schemas/package.json
{
  "name": "@acme/schemas",
  "version": "0.0.1",
  "exports": {
    ".": "./src/index.ts"
  },
  "peerDependencies": {
    "zod": "^3"
  }
}
```

---

## 2. Client Form with React Hook Form + Zod Resolver

```tsx
// apps/web/src/components/ContactForm.tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import type { ContactFormData, ContactApiResponse } from '@acme/schemas';
import { ContactSchema } from '@acme/schemas';

export function ContactForm() {
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting, isSubmitSuccessful },
  } = useForm<ContactFormData>({
    resolver: zodResolver(ContactSchema),
    defaultValues: {
      name: '',
      email: '',
      message: '',
      agreeToTerms: false,
    },
  });

  async function onSubmit(data: ContactFormData) {
    const res = await fetch('/api/contact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    const body: ContactApiResponse = await res.json();

    if (!body.ok) {
      // Map server-side field errors back to RHF
      for (const [field, messages] of Object.entries(body.errors.fieldErrors)) {
        setError(field as keyof ContactFormData, {
          type: 'server',
          message: messages?.[0],
        });
      }
      if (body.errors.formErrors.length) {
        setError('root', { type: 'server', message: body.errors.formErrors[0] });
      }
      return;
    }

    reset();
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate>
      {errors.root && (
        <div role="alert" className="text-red-600 text-sm mb-4">
          {errors.root.message}
        </div>
      )}

      <div className="flex flex-col gap-1 mb-4">
        <label htmlFor="name" className="font-medium">Name</label>
        <input
          id="name"
          {...register('name')}
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'name-error' : undefined}
          className="border rounded px-3 py-2"
        />
        {errors.name && (
          <span id="name-error" role="alert" className="text-red-600 text-sm">
            {errors.name.message}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1 mb-4">
        <label htmlFor="email" className="font-medium">Email</label>
        <input
          id="email"
          type="email"
          {...register('email')}
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? 'email-error' : undefined}
          className="border rounded px-3 py-2"
        />
        {errors.email && (
          <span id="email-error" role="alert" className="text-red-600 text-sm">
            {errors.email.message}
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1 mb-4">
        <label htmlFor="message" className="font-medium">Message</label>
        <textarea
          id="message"
          rows={5}
          {...register('message')}
          aria-invalid={!!errors.message}
          aria-describedby={errors.message ? 'message-error' : undefined}
          className="border rounded px-3 py-2"
        />
        {errors.message && (
          <span id="message-error" role="alert" className="text-red-600 text-sm">
            {errors.message.message}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2 mb-6">
        <input
          id="agreeToTerms"
          type="checkbox"
          {...register('agreeToTerms')}
          aria-invalid={!!errors.agreeToTerms}
        />
        <label htmlFor="agreeToTerms" className="text-sm">I agree to the terms</label>
        {errors.agreeToTerms && (
          <span role="alert" className="text-red-600 text-sm">
            {errors.agreeToTerms.message}
          </span>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="bg-blue-600 text-white px-6 py-2 rounded disabled:opacity-50"
      >
        {isSubmitting ? 'Sending…' : 'Send Message'}
      </button>

      {isSubmitSuccessful && (
        <p className="text-green-600 mt-4">Message sent successfully!</p>
      )}
    </form>
  );
}
```

---

## 3. Workers Validation Endpoint

```typescript
// functions/api/contact.ts
import { ZodError } from 'zod';
import { ContactSchema } from '@acme/schemas';
import type { ContactApiResponse } from '@acme/schemas';

interface Env {
  // D1, KV, queue bindings go here
}

export const onRequestPost: PagesFunction<Env> = async ({ request }) => {
  // 1. Parse body
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ ok: false, errors: { fieldErrors: {}, formErrors: ['Invalid JSON body'] } }, 400);
  }

  // 2. Validate with the same shared Zod schema
  const result = ContactSchema.safeParse(body);

  if (!result.success) {
    const flat = result.error.flatten();
    return jsonResponse(
      {
        ok: false,
        errors: {
          fieldErrors: flat.fieldErrors as Record<string, string[]>,
          formErrors: flat.formErrors,
        },
      } satisfies ContactApiResponse,
      422,
    );
  }

  // 3. Process validated data (send email, write to DB, etc.)
  const { name, email, message } = result.data;

  try {
    // Placeholder: replace with your actual side-effect
    const id = crypto.randomUUID();
    // await env.DB.prepare('INSERT INTO contacts ...').bind(id, name, email, message).run();
    return jsonResponse({ ok: true, id } satisfies ContactApiResponse, 201);
  } catch (err) {
    console.error('Contact submission failed:', err);
    return jsonResponse(
      { ok: false, errors: { fieldErrors: {}, formErrors: ['Server error, please try again'] } },
      500,
    );
  }
};

function jsonResponse(data: unknown, status: number): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}
```

---

## 4. Cross-Field / Async Validation

```typescript
// packages/schemas/src/checkout.ts — cross-field refinement
import { z } from 'zod';

export const CheckoutSchema = z
  .object({
    paymentMethod: z.enum(['card', 'bank_transfer']),
    cardNumber: z.string().optional(),
    iban: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.paymentMethod === 'card' && !data.cardNumber) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Card number is required for card payments',
        path: ['cardNumber'],
      });
    }
    if (data.paymentMethod === 'bank_transfer' && !data.iban) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'IBAN is required for bank transfers',
        path: ['iban'],
      });
    }
  });
```

Server-side async uniqueness check (only on the Worker, not client-side):

```typescript
// functions/api/register.ts
async function validateEmailUniqueness(email: string, env: Env): Promise<boolean> {
  const row = await env.DB.prepare('SELECT 1 FROM users WHERE email = ?').bind(email).first();
  return row === null;
}

// Inside onRequestPost:
const { email } = result.data;
const isUnique = await validateEmailUniqueness(email, env);
if (!isUnique) {
  return jsonResponse(
    {
      ok: false,
      errors: {
        fieldErrors: { email: ['This email address is already registered'] },
        formErrors: [],
      },
    },
    422,
  );
}
```

---

## 5. Testing Shared Schemas

```typescript
// packages/schemas/src/__tests__/contact.test.ts
import { ContactSchema } from '../contact';

describe('ContactSchema', () => {
  const valid = {
    name: 'Alice Dupont',
    email: 'alice@example.com',
    message: 'Hello, this is my message which is long enough.',
    agreeToTerms: true,
  };

  it('accepts valid input', () => {
    expect(ContactSchema.safeParse(valid).success).toBe(true);
  });

  it('rejects short names', () => {
    const r = ContactSchema.safeParse({ ...valid, name: 'A' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.flatten().fieldErrors.name?.[0]).toMatch(/at least 2/);
    }
  });

  it('rejects invalid email', () => {
    const r = ContactSchema.safeParse({ ...valid, email: 'not-an-email' });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.flatten().fieldErrors.email?.[0]).toMatch(/valid email/);
    }
  });

  it('rejects unchecked terms', () => {
    const r = ContactSchema.safeParse({ ...valid, agreeToTerms: false });
    expect(r.success).toBe(false);
  });
});
```

---

## 6. Consuming Errors with React Query (Mutation)

```typescript
// hooks/useContactMutation.ts
import { useMutation } from '@tanstack/react-query';
import type { ContactFormData, ContactApiResponse } from '@acme/schemas';

export function useContactMutation() {
  return useMutation<ContactApiResponse, Error, ContactFormData>({
    mutationFn: async (data) => {
      const res = await fetch('/api/contact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      if (!res.ok && res.status !== 422) {
        throw new Error('Network error');
      }
      return res.json();
    },
  });
}
```

---

## Anti-Patterns

- **Client-only validation with no server re-validation** — JavaScript can be disabled or bypassed. Any data the Worker writes to a database or sends to a third party must be validated server-side regardless of what the client already checked.
- **Two separate schemas** — Maintaining a Yup schema on the client and a different Joi schema in the Worker guarantees drift. Use the shared Zod schema as the single source of truth.
- **Returning generic 400 without field details** — A plain `{ error: "Validation failed" }` forces the client to re-parse the original input to decide which field to highlight. Return `ZodError.flatten()` directly so the client can call `setError` field-by-field.
- **Using `z.parse()` instead of `z.safeParse()` on the server** — `parse()` throws a `ZodError` that you must catch. `safeParse()` always returns a discriminated union, making control flow explicit and preventing unhandled promise rejections in Workers.
- **Putting async validators (DB lookups) in the Zod schema** — Zod's `.superRefine()` supports async, but this makes the schema async everywhere including in the browser where DB calls are impossible. Keep async business-rule checks in the Worker handler, outside the schema.

---

## Gotchas

- **`@hookform/resolvers/zod` version pinning**: The resolver's `zodResolver` signature changed between `react-hook-form` v7.43 and v7.50. Pin both together and update as a unit.
- **Zod v3 vs v4 import paths**: Zod v4 ships as `zod/v4` with a different `z.object` API for strict objects. If your Worker bundle includes both versions via transitive deps you will get confusing schema mismatches. Lock to a single version in the monorepo root `pnpm-workspace.yaml`.
- **`noValidate` on the `<form>` element**: Without this, the browser's native validation dialog appears before RHF's logic fires, giving users two different error UIs. Always add `noValidate` when using custom validation.
- **Workers bundle size**: Zod v3 adds ~13 kB gzipped to a Worker bundle. Keep schema files in a shared package so they are tree-shaken; do not import the entire `zod` namespace if you only use `z.object` and `z.string`.
- **`trim()` on the server, not just the client**: Zod's `.trim()` transformer runs during parsing. Make sure the Worker parses with the same schema so trailing whitespace is stripped before DB writes.

---

## Verification

```bash
# Valid submission
curl -s -X POST https://your-app.pages.dev/api/contact \
  -H 'Content-Type: application/json' \
  -d '{"name":"Alice","email":"a@b.com","message":"Hello world, this is long enough","agreeToTerms":true}' \
  | jq .
# Expected: {"ok":true,"id":"..."}

# Invalid submission — should return field errors
curl -s -X POST https://your-app.pages.dev/api/contact \
  -H 'Content-Type: application/json' \
  -d '{"name":"A","email":"not-email","message":"short","agreeToTerms":false}' \
  | jq .errors.fieldErrors
# Expected: {name:[...], email:[...], message:[...], agreeToTerms:[...]}

# Run shared schema unit tests
pnpm --filter @acme/schemas test
```

---

## Related

- `react-form-handling-react-hook-form.md`
- `html-form-validation.md`
- `react-query-patterns.md`
- `optimistic-ui-updates-rollback.md`
- `typescript-discriminated-unions-ui.md`

---

## Sources

- Zod documentation — https://zod.dev/
- React Hook Form `setError` — https://react-hook-form.com/docs/useform/seterror
- `@hookform/resolvers` — https://github.com/react-hook-form/resolvers
- Cloudflare Pages Functions — https://developers.cloudflare.com/pages/functions/
