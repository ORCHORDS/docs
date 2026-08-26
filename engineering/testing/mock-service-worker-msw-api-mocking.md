# mock-service-worker-msw-api-mocking

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Tests that call `jest.mock('axios')` or `jest.mock('fetch')`
break whenever the HTTP client is swapped out or a new
interceptor is added, requiring test edits unrelated to the
feature under test.

## Context

Mock Service Worker (MSW) intercepts HTTP at the network
level — inside a browser Service Worker or via Node's
`http`/`https` module interception — so the code under test
uses its real HTTP client unchanged. This makes mocks
resilient to client swaps, centralises the fake API
definition, and produces the same handlers in both browser
and server (test runner) environments.

## Installation and Handler Authoring

```bash
npm install -D msw
# Browser: initialise the service worker once
npx msw init public/ --save
```

`src/mocks/handlers.ts` — define REST and GraphQL handlers:

```ts
import { http, HttpResponse, graphql } from 'msw';

export const handlers = [
  // REST — GET
  http.get('/api/users/:id', ({ params }) =>
    HttpResponse.json({ id: params.id, name: 'Alice' })
  ),

  // REST — POST with request body
  http.post('/api/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json(
      { id: crypto.randomUUID(), ...body },
      { status: 201 }
    );
  }),

  // GraphQL
  graphql.query('GetUser', ({ variables }) =>
    HttpResponse.json({
      data: { user: { id: variables.id, name: 'Alice' } },
    })
  ),
];
```

## Server Setup for Vitest and Jest

`src/mocks/server.ts`:

```ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

`src/test/setup.ts` (referenced from `vitest.config.ts`
`setupFiles` or Jest `setupFilesAfterFramework`):

```ts
import { server } from '../mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(()  => server.resetHandlers());
afterAll(()   => server.close());
```

`onUnhandledRequest: 'error'` converts any request not
matched by a handler into a test failure, preventing
silent stubs from masking missing handler definitions.

## Per-test Overrides and Passthrough

Override a handler for a single test without modifying the
shared handler list:

```ts
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

it('shows error banner on 503', () => {
  server.use(
    http.get('/api/users/:id', () =>
      HttpResponse.json(
        { message: 'Service unavailable' },
        { status: 503 }
      )
    )
  );
  // ... render and assert
});
```

Allow a specific endpoint to reach the real network:

```ts
import { passthrough } from 'msw';

http.get('https://cdn.example.com/fonts/*', () =>
  passthrough()
),
```

## Playwright Integration

In Playwright E2E tests, start the service worker inside
the browser by calling `worker.start()` via
`page.evaluate()` before the first navigation, using an
auto-fixture so every test gets it automatically. The
shared `handlers.ts` file drives both the Vitest/Jest unit
layer and the Playwright E2E layer from one definition.

## Why MSW Beats `jest.mock()` for API Layer Testing

| Criterion               | `jest.mock()`      | MSW               |
|-------------------------|--------------------|-------------------|
| HTTP client coupling    | Yes — per client   | None              |
| Works in browser tests  | No                 | Yes               |
| Request body inspection | Manual             | `await req.json()`|
| Unhandled requests fail | No                 | Yes (opt-in)      |
| Shared with E2E layer   | No                 | Yes               |
| Response headers/status | Manual             | First-class       |

## Anti-patterns

- Mocking at the module boundary (`jest.mock('axios')`)
  when MSW is already in the project — two sources of
  truth diverge silently.
- Forgetting `server.resetHandlers()` in `afterEach` —
  per-test `server.use()` overrides bleed into later tests.
- Returning raw objects from handlers — always wrap in
  `HttpResponse.json()` to get correct `Content-Type`.
- Using `onUnhandledRequest: 'warn'` in CI — promote to
  `'error'` so unmatched requests become visible failures.

## Gotchas

- The browser Service Worker must be served from the same
  origin as the app; cross-origin worker registration is
  blocked by browser policy.
- MSW v2 (current) has a different import path from v1
  — `msw/node` and `msw/browser`, not `msw/lib/...`.
- `passthrough` must be imported from `msw`, not
  constructed manually; returning `undefined` from a
  handler causes an unhandled-request error.
- Vitest runs in Node even for browser-mode tests unless
  `environment: 'jsdom'` or `'happy-dom'` is set; ensure
  `msw/node` is used in those environments.
- GraphQL interception matches on `operationName`, not URL
  path, so all GraphQL requests must go to the same
  endpoint for handler routing to work.

## Verification

```bash
# Install and verify handler types compile
npx tsc --noEmit

# Run unit tests with unhandled-request error mode
npx vitest run --reporter=verbose

# Confirm no real network calls escape in CI
# (set onUnhandledRequest: 'error' and check for failures)
```

A passing suite with `onUnhandledRequest: 'error'` proves
every HTTP call is covered by an explicit handler.

## Related

- `testing/mock-server-msw.md`
- `testing/playwright-network-interception.md`
- `testing/mocking-vs-stubbing-vs-spying.md`
- `testing/integration-test-api.md`
- `testing/graphql-testing-patterns.md`

## Source URLs (verified 2026-08-17)

- https://mswjs.io/docs/getting-started
- https://mswjs.io/docs/network-behavior/rest
- https://mswjs.io/docs/network-behavior/graphql
- https://mswjs.io/docs/integrations/node
- https://mswjs.io/docs/integrations/browser
