# API-First Architecture

> **When to use:** When the API is a product—consumed by web, mobile, partners,
> and internal services alike—and breaking it means breaking everyone.

## Symptom

You feel API-first is missing when:

- The web team ships a feature, then the mobile team waits 2 weeks for a
  "mobile-specific" endpoint. Then the partner integration team waits again.
- The API is whatever the backend happened to build, discovered by reading the
  controller source code. There is no contract.
- Versioning is chaos: `/v2/getUserByIdNew`, `/v2/getUserByIdNew2`,
  query-param flags like `?includeEmail=true&newFormat=true`.
- Breaking changes (renaming a field, removing a response property) are
  discovered at runtime in production, not at design time.
- Multiple clients each demand slightly different shapes, so the backend
  sprouts `if (client === 'mobile')` branches everywhere.
- The OpenAPI spec, if it exists, was generated from code after the fact and
  is perpetually out of date.

These are symptoms of **code-first**, where the API is an afterthought. The
fix is API-first: the contract is designed, reviewed, and frozen *before* any
implementation.

## Core Idea

The API contract (OpenAPI, GraphQL SDL, gRPC `.proto`) is the single source
of truth. It is authored first, reviewed by all stakeholders, and then:

1. **Clients** generate types, mocks, and SDKs from the contract immediately.
   Frontend work proceeds against mocked endpoints in parallel with backend.
2. **Servers** generate stubs, validators, and route handlers from the same
  contract.
3. **Tests** are derived from the contract (contract testing with Pact,
   Dredd, Schemathesis).
4. **Docs** are generated, not hand-written.

```
[OpenAPI spec] --generate--> [TS client types]      (frontend, day 1)
               --generate--> [server stubs]          (backend, day 1)
               --generate--> [Prism mocks]           (frontend, day 1)
               --generate--> [reference docs]        (everyone)
               --verify--->   [contract tests in CI] (gate deploys)
```

## Gotchas

- **The spec rots the moment you stop enforcing it.** Code-first drift
  returns silently. Wire the contract into CI: a PR that changes the
  controller without updating the spec fails the build. Use
  `openapi-diff` to detect breaking changes.
- **Versioning is a design decision, not an afterthought.** Decide upfront:
  URI versioning (`/v1/`), header versioning, or media-type versioning.
  Document the deprecation policy (e.g. "N-1 supported, 6-month sunset").
  See `api-versioning-strategy.md`.
- **Generating clients for every language is seductive but expensive.** Each
  generated SDK needs testing, publishing, versioning, and a maintainer.
  Generate for the languages you actually support; for everyone else, point
  them at the spec and let them generate their own.
- **Mocks drift from reality if not validated.** Prism/Stoplight mocks are
  great until the real backend returns a different shape. Contract tests
  (Pact) close this gap—do not skip them.
- **Backward compatibility is a discipline, not a hope.** Adding a required
  field to a request body is a breaking change. Removing any response field
  is a breaking change. Adding optional fields is safe. Use
  `oasdiff --breaking-only` in CI to catch these.
- **REST vs GraphQL vs gRPC is not a religious war—it's a fit question.**
  REST for resource-oriented public APIs, GraphQL for many-client flexible
  queries, gRPC for internal high-throughput polyglot services. See
  `grpc-vs-rest-vs-graphql.md`.
- **Pagination, filtering, errors, and rate limiting must be consistent
  across the entire API.** Inconsistent error shapes (`{error: "..."}` vs
  `{message: "..."}` vs RFC 7807) are the #1 client complaint. Standardize
  once in a shared spec component.
- **Authentication belongs in the spec, not in prose docs.** Use OpenAPI
  security schemes (`Bearer`, `OAuth2`, `apiKey`) so generated clients handle
  auth automatically.
- **API gateways are not a substitute for a contract.** A gateway enforces
  traffic policy (rate limits, auth) but does not define the shape. Author
  the contract first; configure the gateway from it.

## Practical Example

**Step 1 — Author the contract first (OpenAPI):**

```yaml
# openapi.yaml — written BEFORE any backend code
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /v1/orders:
    post:
      operationId: createOrder
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/CreateOrderRequest" }
      responses:
        "201":
          description: Created
          content:
            application/json:
              schema: { $ref: "#/components/schemas/Order" }
components:
  schemas:
    CreateOrderRequest:
      type: object
      required: [customerId, items]
      properties:
        customerId: { type: string }
        items:
          type: array
          items: { $ref: "#/components/schemas/OrderItem" }
    OrderItem:
      type: object
      required: [sku, quantity]
      properties:
        sku: { type: string }
        quantity: { type: integer, minimum: 1 }
```

**Step 2 — Frontend generates types and works against mocks on day 1:**

```bash
openapi-typescript ./openapi.yaml -o ./src/types/api.ts   # typed client
prism mock ./openapi.yaml -p 4010                          # mock server
```

**Step 3 — Backend generates the server stub and validates every request:**

```typescript
// Express + OpenAPI validator middleware
import * as OpenApiValidator from "express-openapi-validator";
app.use(OpenApiValidator.middleware({ apiSpec: "./openapi.yaml" }));
```

**Step 4 — CI gates breaking changes:**

```bash
# Fail the build if the PR introduces a breaking change vs main
oasdiff breaking main.yaml pr.yaml && echo "OK" || exit 1
```

## When NOT to go API-first

- **Prototypes and throwaways.** The upfront contract cost is wasted if the
  shape will change 10 times this week.
- **Single-consumer internal tools.** If only your own frontend talks to your
  own backend, the overhead may not pay off—though even there, generated
  types usually win.

## Decision Checklist

1. Are there 2+ independent consumers (web, mobile, partner)? -> API-first
2. Do you ship SDKs in multiple languages? -> API-first
3. Are breaking changes discovered in production today? -> API-first
4. Is this a short-lived prototype? -> Code-first is fine
5. Will the API be exposed publicly or to partners? -> API-first, non-negotiable

## Related Articles

- `contract-first-api-design.md` — sibling concept, contract authored first
- `openapi-spec-driven-development.md` — OpenAPI-specific workflow
- `api-versioning-strategy.md` — how to evolve without breaking clients
- `grpc-vs-rest-vs-graphql.md` — choosing the API style
- `api-security-architecture.md` — auth and threat model for APIs
