# contract-testing

**Issue:** Catch API contract breaks between services + clients
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your backend changes a response field. The mobile app expects
the old shape. The app crashes in production. You have no
test that catches this.

## Root cause
**API contracts are not enforced.** A backend can change
without the client knowing. A client can assume without the
backend validating.

**Source:** Pact — Contract testing:
https://pact.io/

> "Contract testing is a way to ensure that two applications
> (a provider and a consumer) are compatible by checking
> that the provider's responses match the consumer's
> expectations."

## The 3 levels of contract testing

### Level 1: Schema validation (response shape)
- **What:** The response has the expected fields and types
- **Tools:** JSON Schema, Zod, TypeScript types
- **Where:** In the provider's own tests

```ts
// In the backend's test
const response = await fetch('/api/users/u_123');
const body = await response.json();

const userSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  displayName: z.string(),
  role: z.enum(['viewer', 'admin', 'owner']),
});

expect(userSchema.parse(body)).toEqual(body);  // Throws if mismatch
```

### Level 2: Consumer-driven contract (the Pact pattern)
- **What:** The consumer's expectations are recorded as a
  contract; the provider verifies the contract
- **Tools:** Pact, Spring Cloud Contract
- **Where:** Both consumer and provider have tests

```ts
// Consumer test (mobile app, web app, etc.)
import { Pact } from '@pact-foundation/pact';

const provider = new Pact({
  consumer: 'mobile-app',
  provider: 'user-service',
});

describe('user-service contract', () => {
  it('returns the expected user shape', async () => {
    await provider.addInteraction({
      state: 'a user exists with id u_123',
      uponReceiving: 'a request for the user',
      withRequest: { method: 'GET', path: '/api/users/u_123' },
      willRespondWith: {
        status: 200,
        body: { id: 'u_123', email: 'alice@example.com', displayName: 'Alice', role: 'admin' },
      },
    });

    // Test the consumer
    const response = await fetch('http://localhost:1234/api/users/u_123');
    expect(response.status).toBe(200);

    await provider.verify();
  });
});
```

The provider then runs the generated contract to verify it
can satisfy the consumer's expectations:
```ts
// Provider test
import { Verifier } from '@pact-foundation/pact';

const verifier = new Verifier({
  provider: 'user-service',
  providerBaseUrl: 'http://localhost:3000',
});

await verifier.verifyProvider();  // Runs the recorded contracts
```

### Level 3: E2E contract (real integration)
- **What:** The consumer + provider are tested together
- **Tools:** Playwright, Cypress
- **Where:** CI after a deploy

## When to use which

✅ Use **Level 1 (schema)** when:
- You have one team owning both
- The contract is simple
- You want fast feedback in the dev loop

✅ Use **Level 2 (Pact)** when:
- You have separate teams (mobile, web, backend)
- The consumer is decoupled from the provider
- You want CI-enforced compatibility

✅ Use **Level 3 (E2E)** when:
- You have a deployable environment
- The contract is complex
- You want full integration coverage

## Schema validation as code

The cheapest and most maintainable contract test is **types**.

```ts
// shared types
export interface User {
  id: string;
  email: string;
  displayName: string;
  role: 'viewer' | 'developer' | 'compliance_officer' | 'admin' | 'owner';
}

// The backend uses this type for the response
export async function getUser(req: Request, env: Env): Promise<Response> {
  const user = await db.first<User>(`SELECT * FROM users WHERE id = ?`, id);
  return jsonOk(user);
}

// The frontend uses this type for the response
const res = await fetch('/api/users/u_123');
const user: User = await res.json();  // TypeScript verifies the shape
```

If the backend changes `role` from `'admin'` to `'administrator'`,
TypeScript catches the mismatch in the consumer code at compile
time.

## The "breaking change" detection

A breaking change is a change that doesn't match the
contract. Common examples:
- Removing a field
- Renaming a field
- Changing a field's type
- Adding a new required field

Schema validation + TypeScript catches all of these.

## Verification
- **Test:** `test/contract.test.ts > every API response matches
  the documented schema` — passes
- **Live:** A breaking change in production causes a CI failure
  in the consumer
- **Audit:** Quarterly review of API changes

## Gotchas
- **The contract is a living document.** As the API evolves,
  the contract must evolve. Don't let the contract rot.
- **The consumer's expected contract may be wrong.** A consumer
  test that's always green (because it expects the wrong
  thing) is a false sense of security.
- **Pact contracts can be heavy.** Each interaction is a
  recorded test. For 100 endpoints, you have 100 contracts.
  Manage them carefully.
- **Pact + D1 is hard to test.** The D1 state must be set up
  before each contract test. Use the same test fixtures as
  the provider's own tests.
- **The schema validates shape, not behavior.** A 200 response
  with the wrong data passes schema validation. Use
  integration tests for behavior.

## Related
- `api-versioning.md` (when to bump versions)
- `event-driven-architecture.md` (the contract is the event
  schema)
- Pact: https://pact.io/
- OpenAPI: https://www.openapis.org/
