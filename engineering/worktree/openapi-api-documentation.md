# OpenAPI and API Documentation

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your API has no machine-readable specification. Documentation is manually
maintained in a wiki or README, drifts from the implementation, and cannot
be used to auto-generate client SDKs, test stubs, or validation middleware.
New developers spend hours reading source code to understand request/response
shapes.

## Context

OpenAPI 3.1 (aligned with JSON Schema 2020-12) is the de facto standard for
describing REST APIs. An OpenAPI spec is a YAML or JSON file that is both
human-readable documentation and a machine-readable contract. The spec drives
the entire API tooling ecosystem: documentation rendering, SDK generation,
request validation, mock servers, and contract testing.

## API-first workflow

1. **Design** — write the OpenAPI spec before writing code. Use a visual
   editor (Stoplight Studio, Swagger Editor) or write YAML directly.
2. **Lint** — validate the spec against style rules using Spectral.
3. **Review** — PR review the spec alongside code changes.
4. **Generate** — auto-generate server stubs, client SDKs, and validation
   middleware from the spec.
5. **Test** — contract-test the implementation against the spec.
6. **Publish** — render interactive documentation with Scalar, Redocly, or
   Swagger UI.

## Documentation renderers (2026)

| Tool | Strengths | License |
|---|---|---|
| **Scalar** | Modern UI, dark mode, interactive try-it, fast | MIT |
| **Redocly (Redoc)** | Polished three-panel layout, best visual quality | Open-source (Redoc) / commercial (platform) |
| **Swagger UI** | Industry standard, most recognized | Apache 2.0 |
| **Mintlify** | Docs-as-code platform, MDX support, search | Commercial |
| **Stoplight Elements** | Embeddable, React component | Apache 2.0 |

## Spectral linting

Spectral (Stoplight) is the standard linter for OpenAPI specs. It enforces
style consistency across teams.

```yaml
# .spectral.yml
extends: spectral:oas
rules:
  operation-operationId: error
  operation-description: warn
  info-contact: error
  oas3-valid-schema-example: error

  # Custom rule: require request body examples
  request-body-example:
    given: "$.paths.*.*.requestBody.content.*.schema"
    then:
      field: example
      function: truthy
    severity: warn
    message: "Request body schemas should include an example"
```

```bash
# Run Spectral in CI
npx @stoplight/spectral-cli lint openapi.yaml --fail-severity warn
```

## Code generation

```bash
# Generate TypeScript client from OpenAPI spec
npx openapi-typescript openapi.yaml -o src/api/schema.d.ts

# Generate Go server stubs
oapi-codegen -generate types,server -package api openapi.yaml > api/server.gen.go

# Generate Python client with openapi-generator
openapi-generator-cli generate -i openapi.yaml -g python -o ./client
```

## Anti-patterns

- **Spec-after-code** — generating the spec from code annotations produces
  specs that mirror implementation details, not the designed API contract.
  Design first, implement second.
- **One giant spec file** — split large APIs using `$ref` to external files.
  Organize by domain (`users.yaml`, `orders.yaml`).
- **Undocumented error responses** — document all error response schemas
  (400, 401, 403, 404, 409, 422, 500). Clients need to handle them.
- **Missing examples** — specs without request/response examples are
  unusable for developers. Add examples to every schema.
- **Ignoring spec drift** — if the spec and implementation diverge, contract
  tests fail. Run contract tests in CI to catch drift immediately.

## Gotchas

- **OpenAPI 3.1 vs. 3.0** — 3.1 aligns with JSON Schema 2020-12 (adds
  `null` type, `$dynamicRef`). Some tools (older Swagger UI, some code
  generators) still only support 3.0. Check tool compatibility.
- **AsyncAPI for event-driven APIs** — OpenAPI covers REST. For WebSocket,
  Kafka, AMQP, or MQTT APIs, use AsyncAPI (complementary standard).
- **Spec size limits** — very large specs (10K+ lines) slow down editors and
  renderers. Use `$ref` splitting and lazy loading.
- **Authentication documentation** — document security schemes
  (`securitySchemes`) at the spec level, not just in prose. Tools use this
  for try-it-out authentication.

## Verification

- Spectral lint passes with zero errors in CI.
- Contract tests (Prism, Dredd, or Schemathesis) verify the implementation
  matches the spec.
- Generated client SDK compiles and passes type checks.
- Documentation site renders correctly and all endpoints are explorable.

## Related

- `documentation/categories/testing/contract-testing-pact.md`
- `documentation/categories/testing/schema-driven-api-fuzzing-schemathesis.md`
- `documentation/categories/patterns/webhook-implementation.md`
- `documentation/categories/deploy/api-versioning-2026.md`

## Source URLs (verified 2026-08-16)

- Best OpenAPI tools and documentation platforms 2026 — https://zuplo.com/learning-center/best-openapi-tools-2026
- Scalar vs Redoc vs Swagger UI 2026 — https://www.pkgpulse.com/guides/scalar-vs-redoc-vs-swagger-ui-api-documentation-2026
- API documentation: OpenAPI vs AsyncAPI 2026 — https://apiscout.dev/guides/api-documentation-openapi-vs-asyncapi-2026
- Best Swagger alternatives 2026 — https://dev.to/therealmrmumba/10-best-swagger-alternatives-for-api-design-testing-and-documentation-in-2026-3nl5
