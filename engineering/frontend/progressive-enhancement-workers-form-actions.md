# Progressive Enhancement with Cloudflare Workers Form Actions

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

Your form works perfectly with JavaScript enabled but silently fails or shows a blank page when JS is blocked, slow to load, or errored. You need the form submission to succeed with plain HTML and then layer on client-side UX improvements (optimistic feedback, inline validation, no-reload submission) as a progressive enhancement.

## Context

Progressive enhancement starts with a working HTML `<form action="…" method="post">` that submits to a Cloudflare Worker or Pages Function endpoint. The endpoint returns either a redirect (PRG pattern) for the HTML path or JSON for the JS-enhanced path. A thin client-side script intercepts the submit event, calls the same endpoint with `fetch`, and renders feedback inline — without requiring the script to be present for the form to function.

This pattern is particularly effective on Cloudflare Pages because the same Worker URL handles both the HTML form POST and the `fetch` JSON request, keeping backend logic in one place.

---

## Baseline HTML Form (No JavaScript)

The form must work as a native POST. The Worker detects `Accept: text/html` to return a redirect.

```html
<!-- public/contact.html -->
<form action="/api/contact" method="post" novalidate>
  <label for="email">Email</label>
  <input id="email" name="email" type="email" required autocomplete="email" />

  <label for="message">Message</label>
  <textarea id="message" name="message" required minlength="10"></textarea>

  <button type="submit">Send message</button>
</form>
```

```typescript
// functions/api/contact.ts
import type { PagesFunction } from '@cloudflare/workers-types';

interface Env {
  CONTACT_KV: KVNamespace;
}

interface FormData {
  email: string;
  message: string;
}

function parseFormBody(text: string): FormData {
  const params = new URLSearchParams(text);
  return {
    email: params.get('email') ?? '',
    message: params.get('message') ?? '',
  };
}

function validate(data: FormData): string[] {
  const errors: string[] = [];
  if (!data.email.includes('@')) errors.push('Valid email required.');
  if (data.message.length < 10) errors.push('Message must be at least 10 characters.');
  return errors;
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const contentType = request.headers.get('content-type') ?? '';
  const acceptsHtml = (request.headers.get('accept') ?? '').includes('text/html');
  const isJson = contentType.includes('application/json');

  let data: FormData;
  if (isJson) {
    data = (await request.json()) as FormData;
  } else {
    data = parseFormBody(await request.text());
  }

  const errors = validate(data);

  if (errors.length > 0) {
    if (acceptsHtml && !isJson) {
      // PRG failure – redirect back with error param
      return Response.redirect(
        `/contact?error=${encodeURIComponent(errors.join(' '))}`,
        303,
      );
    }
    return Response.json({ ok: false, errors }, { status: 422 });
  }

  await env.CONTACT_KV.put(
    `contact:${Date.now()}`,
    JSON.stringify(data),
    { expirationTtl: 60 * 60 * 24 * 30 },
  );

  if (acceptsHtml && !isJson) {
    return Response.redirect('/contact?success=1', 303);
  }
  return Response.json({ ok: true });
};
```

---

## Enhancement Layer: Fetch Interception

The script is loaded with `defer` so the form already works before the script runs. If the script errors, the form falls back to native POST.

```typescript
// public/contact-enhance.ts (compiled to /contact-enhance.js)
const form = document.querySelector<HTMLFormElement>('form[action="/api/contact"]');
if (!form) throw new Error('Form not found');

const statusEl = document.createElement('p');
statusEl.setAttribute('aria-live', 'polite');
statusEl.setAttribute('role', 'status');
form.appendChild(statusEl);

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const button = form.querySelector<HTMLButtonElement>('button[type="submit"]');
  if (button) {
    button.disabled = true;
    button.textContent = 'Sending…';
  }
  statusEl.textContent = '';

  try {
    const res = await fetch(form.action, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(Object.fromEntries(new FormData(form))),
    });

    const json = (await res.json()) as { ok: boolean; errors?: string[] };

    if (json.ok) {
      statusEl.textContent = 'Message sent! We'll be in touch.';
      form.reset();
    } else {
      statusEl.textContent = json.errors?.join(' ') ?? 'Submission failed.';
    }
  } catch {
    // Network error – let the native form submission handle it
    form.submit();
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = 'Send message';
    }
  }
});
```

```html
<!-- Load after the form; defer ensures it doesn't block render -->
<script  defer></script>
```

---

## Inline Validation Enhancement

Layer client-side validation on top without removing the server-side check.

```typescript
// Extend the enhancement script
const emailInput = form.querySelector<HTMLInputElement>('#email');
const messageInput = form.querySelector<HTMLTextAreaElement>('#message');

function showFieldError(input: HTMLElement, message: string) {
  let errorEl = document.getElementById(`${input.id}-error`);
  if (!errorEl) {
    errorEl = document.createElement('span');
    errorEl.id = `${input.id}-error`;
    errorEl.setAttribute('role', 'alert');
    errorEl.style.color = 'var(--color-error, red)';
    input.insertAdjacentElement('afterend', errorEl);
  }
  errorEl.textContent = message;
  input.setAttribute('aria-describedby', errorEl.id);
  input.setAttribute('aria-invalid', 'true');
}

function clearFieldError(input: HTMLElement) {
  const errorEl = document.getElementById(`${input.id}-error`);
  if (errorEl) errorEl.textContent = '';
  input.removeAttribute('aria-invalid');
}

emailInput?.addEventListener('blur', () => {
  if (emailInput.value && !emailInput.value.includes('@')) {
    showFieldError(emailInput, 'Enter a valid email address.');
  } else {
    clearFieldError(emailInput);
  }
});

messageInput?.addEventListener('input', () => {
  if (messageInput.value.length > 0 && messageInput.value.length < 10) {
    showFieldError(messageInput, `${10 - messageInput.value.length} more characters needed.`);
  } else {
    clearFieldError(messageInput);
  }
});
```

---

## Remix Progressive Enhancement Pattern on Workers

Remix's `<Form>` component works identically with and without JS when deployed to Cloudflare Workers.

```typescript
// app/routes/contact.tsx
import { Form, useActionData, useNavigation } from '@remix-run/react';
import type { ActionFunctionArgs } from '@remix-run/cloudflare';

export async function action({ request, context }: ActionFunctionArgs) {
  const form = await request.formData();
  const email = String(form.get('email') ?? '');
  const message = String(form.get('message') ?? '');

  if (!email.includes('@')) {
    return Response.json({ error: 'Valid email required.' }, { status: 422 });
  }

  await context.cloudflare.env.CONTACT_KV.put(
    `contact:${Date.now()}`,
    JSON.stringify({ email, message }),
  );

  return Response.json({ ok: true });
}

export default function Contact() {
  const data = useActionData<typeof action>();
  const nav = useNavigation();
  const submitting = nav.state === 'submitting';

  return (
    // Without JS this renders as a plain <form method="post">
    <Form method="post">
      <input name="email" type="email" required />
      <textarea name="message" required minLength={10} />
      {data && 'error' in data && <p role="alert">{data.error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Sending…' : 'Send message'}
      </button>
    </Form>
  );
}
```

---

## Handling File Uploads Progressively

Native file inputs work without JS; `fetch` with `FormData` adds progress feedback.

```typescript
const fileInput = form.querySelector<HTMLInputElement>('input[type="file"]');
const progressBar = document.createElement('progress');
progressBar.max = 100;
progressBar.hidden = true;
fileInput?.insertAdjacentElement('afterend', progressBar);

async function uploadWithProgress(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        progressBar.hidden = false;
        progressBar.value = (e.loaded / e.total) * 100;
      }
    };
    xhr.onload = () => {
      progressBar.hidden = true;
      if (xhr.status === 200) resolve(JSON.parse(xhr.responseText).url as string);
      else reject(new Error(`Upload failed: ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error('Network error'));
    const fd = new FormData();
    fd.append('file', file);
    xhr.send(fd);
  });
}
```

---

## Anti-patterns

- **Removing `action` and `method` attributes** – without these, the HTML form is broken when JS fails; always keep them pointing at the real endpoint.
- **`e.preventDefault()` without a try/catch fallback** – if `fetch` throws, the user is stuck; always call `form.submit()` in the catch block.
- **Sending `application/x-www-form-urlencoded` from `fetch`** – prefer `application/json` for the JS path so the Worker can distinguish fetch vs. native POST by `content-type`.
- **Returning a 200 with an error body for the HTML path** – browsers follow redirects automatically; a 303 redirect is the correct response for the PRG pattern.
- **Replacing `<form>` with a JS-only widget** – SPAs that remove the `<form>` element break native autofill, password managers, and accessibility tools.

---

## Gotchas

- Cloudflare Pages Functions have a 25 MB request body limit; handle large file uploads via signed R2 URLs instead of passing through the Worker.
- `new URLSearchParams(text)` does not handle multipart form data (file uploads); use a library or require JS for multipart paths.
- The `novalidate` attribute on the form disables built-in browser validation, allowing the server to control error messages; remove it if you want native popups as the no-JS fallback.
- Remix's `useNavigation` state only reflects JS-enhanced submissions; server-rendered redirects on the no-JS path bypass it entirely.
- Double-submissions are possible if a user clicks submit twice before JS intercepts; set `button.disabled = true` immediately on submit.

---

## Verification

```bash
# Test no-JS path: disable JS in DevTools and submit the form
# The page should redirect to /contact?success=1

# Test JSON path directly
curl -s -X POST https://your-site.pages.dev/api/contact \
  -H 'Content-Type: application/json' \
  -d '{"email":"test@example.com","message":"Hello from curl"}' | jq .

# Test validation error
curl -s -X POST https://your-site.pages.dev/api/contact \
  -H 'Content-Type: application/json' \
  -d '{"email":"not-an-email","message":"short"}' | jq .errors
```

Use Playwright to run both paths in the same test suite:

```typescript
test('form works without JS', async ({ page, context }) => {
  await context.setJavaScriptEnabled(false);
  await page.goto('/contact');
  await page.fill('#email', 'test@example.com');
  await page.fill('#message', 'Hello from playwright test');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/success=1/);
});
```

---

## Related

- `form-validation-zod-workers-endpoint.md`
- `remix-cloudflare-workers-adapter.md`
- `react-server-actions.md`
- `hono-cloudflare-workers-frontend-api.md`
- `html-form-validation.md`

---

## Sources

- https://developers.cloudflare.com/pages/functions/
- https://remix.run/docs/en/main/guides/form-validation
- https://developer.mozilla.org/en-US/docs/Glossary/Progressive_Enhancement
- https://web.dev/articles/progressively-enhance-your-progressive-web-app
