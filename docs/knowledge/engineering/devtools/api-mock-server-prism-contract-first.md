# Api Mock Server Prism Contract First

A contract-first API workflow treats the OpenAPI document as the source
of truth: the spec is written or generated before the handler code, and
both the client and the server are validated against it. Stoplight
Prism is the tool that makes the spec executable locally. It runs a mock
HTTP server directly from an OpenAPI description, returning examples or
dynamically generated responses that conform to the schema, rejecting
requests that violate the contract, and acting as a validation proxy in
front of a real backend. Frontend teams stop waiting for staging, and
contract drift is caught before code review.

## Scope

Using Prism as a local mock server and contract validator for HTTP APIs
described by OpenAPI 2.0 (Swagger) or 3.x documents: running it from the
CLI, choosing response strategies, wiring it into dev scripts, and
enforcing the contract in CI. Not covered: full service virtualization
suites, stateful SOAP mocking, or backend code generation.

## Workflow or implementation guidance

1. **Install and run the mock in one command.** Prism ships as a Docker
   image and an npm package, so a repository needs no global install:

   ```bash
   npx @stoplight/prism-cli mock openapi.yaml --port 4010 --dynamic
   docker run --rm -p 4010:4010 stoplight/prism:4 mock /tmp/openapi.yaml -p 4010 --dynamic
   ```

   Every path and operation declared in the document is immediately
   served, including 404-with-schema behavior for undeclared routes.
2. **Understand the three response strategies.** Default behavior
   returns the first `example` or `default` defined in the spec for a
   response. With `--dynamic`, Prism generates response bodies from the
   JSON Schema, honoring constraints like `minimum`, `pattern`, and
   `enum`. Client-driven selection uses the `Prefer` request header, so
   a frontend can request a specific status or example:

   ```bash
   curl localhost:4010/users/42 -H 'Prefer: code=404'
   curl localhost:4010/users/42 -H 'Prefer: example=premium-user'
   ```

   Dynamic mode plus `Prefer` covers most "what does the UI do when the
   API errors" testing without any backend.
3. **Keep examples authoritative for humans.** Dynamic responses are
   schema-valid but nonsense-shaped; real hand-written examples in the
   spec read better in demos and snapshot tests. The practical split is
   examples for the golden paths and dynamic generation for edge and
   error cases you would never hand-write.
4. **Use mock as the default dev dependency for new frontends.** Point
   the app at `http://localhost:4010` through the environment layer, so
   the only switch between mock, staging, and production is a variable.
   A `mock` npm script that starts Prism and watches the spec file gives
   contract changes an instant feedback loop.
5. **Run the proxy for contract enforcement.** Prism's proxy mode
   forwards traffic to a real upstream and validates both directions
   against the spec, logging violations without blocking by default:

   ```bash
   npx @stoplight/prism-cli proxy openapi.yaml https://staging.api.internal --upstream --errors
   ```

   Running the test suite through the proxy during development catches
   undocumented fields and wrong status codes while the change is still
   open in the editor.
6. **Gate the spec itself in CI.** Contract-first only works if the
   document is valid and linted. Add spectral-style linting plus Prism
   validation jobs to CI so a merged spec is always mockable, and treat
   a spec that fails to boot Prism as a broken build.

## Controls

- **Spec ownership.** One OpenAPI document per service, owned by the
  service team, reviewed in pull requests like code. Generated documents
  (for example from Hono or zod schemas) must be regenerated in CI, not
  hand-edited.
- **Port and environment conventions.** Fix the mock port per repository
  and expose it through the same environment mechanism as production
  URLs, so no code branches on "am I mocked".
- **Prefer-header usage policy.** Document which `Prefer` codes the team
  uses for negative testing; a scattered set of one-off headers becomes
  untestable noise.
- **Version pinning.** Pin the Prism version in devDependencies or the
  Docker digest, because response-generation behavior differs between
  major versions and snapshot tests will churn on upgrades.

## Validation evidence

After starting the mock, a working setup passes these checks:

1. `curl -i localhost:4010/health` returns the documented status and
   content type for that operation, proving the spec is loaded and the
   path matches.
2. Sending a request that violates a required field or type in the
   request schema returns a 422 with a Prism validation payload, proving
   request validation is active rather than pass-through.
3. Requesting an undocumented path returns Prism's structured
   no-operation response rather than a connection error.
4. `Prefer: code=500` returns a 500 body that still validates against
   the declared error schema, proving error contracts are real.
5. In CI, the job that runs Prism against the committed spec exits zero;
   introduce a deliberate schema error in a branch and confirm the job
   fails before merge.

## Failure modes and correction

- **Mock returns 404 for a known path.** Usually a mismatch in method,
  server base path, or an `servers` entry in the document; compare the
  exact URL Prism logs on startup with the request path.
- **Dynamic responses look wrong.** The schema lacks constraints, so
   generated strings and numbers are legal but useless. Tighten the
   schema with `pattern`, `format`, `minLength`, and examples rather
   than disabling dynamic mode.
- **Proxy silently passes invalid responses.** Without `--errors`, Prism
   logs but does not fail on contract violations; enable strict mode in
   CI and keep it advisory locally.
- **Spec drift between mock and reality.** The mock can only be as
   truthful as the document. When the backend is the truth, generate
   the document from code and validate with the proxy; when the
   document is the truth, generate server stubs and types from it. Pick
   one direction per service and write it down.
- **Slow startup on large specs.** Split monolithic documents with
   external `$ref` folders so Prism loads only the served domain, and
   keep mock runs scoped per frontend app.

## Limitations

- Prism is stateless between requests; login flows, pagination
  sequences, and "create then read the same resource" scenarios need
   examples or a different tool.
- Authentication schemes are validated structurally but Prism will not
  mint real tokens; OAuth-protected flows degrade to static headers.
- Contract-first mocking does not verify business logic; a green mock
  only proves the shape of the conversation.

## Canonical sources

- Stoplight Prism GitHub repository: https://github.com/stoplightio/prism
- Stoplight, API mocking with Prism: https://stoplight.io/api-mocking/
- Stoplight documentation hub: https://docs.stoplight.io/
