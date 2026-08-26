# msw-api-mocking

**Issue:** Tests and Storybook stories make real API calls or require manual fetch mocking
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Tests fail in CI because the backend is not running; mocking fetch globally is brittle.

## Pattern / Solution
```ts
// src/mocks/handlers.ts
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users', () => {
    return HttpResponse.json([{ id: 1, name: 'Alice' }]);
  }),
  http.post('/api/posts', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json({ id: 2, ...body }, { status: 201 });
  }),
];

// src/mocks/browser.ts
import { setupWorker } from 'msw/browser';
export const worker = setupWorker(...handlers);

// src/mocks/server.ts (Node.js / Vitest)
import { setupServer } from 'msw/node';
export const server = setupServer(...handlers);
```

## Gotchas
- MSW intercepts at the network level; no fetch/axios mocking needed
- Use server.use(http.get(...)) inside a test to override the default handler
- Storybook MSW addon requires the Service Worker to be set up in public/

## Related
- `testing-library-patterns.md`
- `browser-fetch-patterns.md`
