# Contract Testing with Pact for Workers API

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Consumer teams break silently when the example project Workers API changes a response shape. Integration suites only catch mismatches after a full deploy; mobile clients carry stale assumptions about field names and nullable unions.

## Context

example project runs its API layer on Cloudflare Workers. Consumers include a React Pages front-end, iOS/Android mobile clients, and internal micro-consumers. Pact's consumer-driven contract model lets each consumer publish the exact interaction shape it depends on; the Workers provider verifies those shapes in isolation without network round-trips.

Pact version used: `@pact-foundation/pact` 12.x with the Pact Broker hosted on pactflow.io. Provider verification runs inside `vitest` using a local Miniflare instance of the Worker.

## Consumer Setup

Install dependencies on the consumer side (React Pages or mobile BFF):

```bash
npm install --save-dev @pact-foundation/pact
```

Minimal consumer test — React Pages fetching `/api/tracks`:

```typescript
// tests/pact/tracks.consumer.pact.ts
import path from "node:path";
import { PactV3, MatchersV3 } from "@pact-foundation/pact";
import { fetchTracks } from "../../src/api/tracks";

const { like, eachLike, integer, string } = MatchersV3;

const provider = new PactV3({
  consumer: "example project-pages",
  provider: "example project-workers-api",
  dir: path.resolve(__dirname, "../../pacts"),
  logLevel: "warn",
});

describe("Tracks API contract", () => {
  it("returns a list of tracks with required fields", async () => {
    await provider
      .given("tracks exist")
      .uponReceiving("GET /api/tracks")
      .withRequest({ method: "GET", path: "/api/tracks" })
      .willRespondWith({
        status: 200,
        headers: { "Content-Type": "application/json" },
        body: eachLike({
          id: integer(1),
          title: string("My Track"),
          durationMs: integer(240000),
          streamUrl: string("https://cdn.example.com/tracks/1.mp3"),
        }),
      })
      .executeTest(async (mockServer) => {
        const tracks = await fetchTracks(mockServer.url);
        expect(tracks.length).toBeGreaterThan(0);
        expect(tracks[0]).toHaveProperty("streamUrl");
      });
  });
});
```

| Option        | Value                             | Purpose                              |
|---------------|-----------------------------------|--------------------------------------|
| `consumer`    | `"example project-pages"`                    | Identifies the consuming application |
| `provider`    | `"example project-workers-api"`              | Must match provider name in broker   |
| `dir`         | `./pacts`                         | Output directory for pact JSON files |
| `logLevel`    | `"warn"`                          | Reduces noise in CI output           |

## Provider Verification in Workers

The provider test spins up the Worker under Miniflare and points Pact at it:

```typescript
// tests/pact/provider.pact.ts
import { PactV3 } from "@pact-foundation/pact";
import { Miniflare } from "miniflare";
import path from "node:path";

let mf: Miniflare;

beforeAll(async () => {
  mf = new Miniflare({
    scriptPath: "./dist/worker.js",
    modules: true,
    d1Databases: ["DB"],
  });
  await seedD1(mf); // insert fixture tracks
});

afterAll(() => mf.dispose());

const verifier = new PactV3({
  provider: "example project-workers-api",
  providerBaseUrl: "http://localhost:8788",
  pactUrls: [path.resolve(__dirname, "../../pacts/example project-pages-example project-workers-api.json")],
  stateHandlers: {
    "tracks exist": async () => {
      await seedD1(mf);
    },
    "no tracks": async () => {
      await truncateTracks(mf);
    },
  },
  logLevel: "warn",
});

describe("example project-workers-api provider verification", () => {
  it("satisfies all consumer pacts", () => verifier.verifyProvider());
});
```

Provider states map to `given(...)` clauses. Each state handler resets D1 fixture data so verification is deterministic.

## Pact Broker Publish in CI

```yaml
# .github/workflows/pact.yml
name: Pact

on: [push]

jobs:
  consumer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - run: npm test -- --testPathPattern=pact/tracks.consumer
      - name: Publish pact
        run: |
          npx pact-broker publish ./pacts \
            --broker-base-url=${{ secrets.PACT_BROKER_URL }} \
            --broker-token=${{ secrets.PACT_BROKER_TOKEN }} \
            --consumer-app-version=${{ github.sha }} \
            --tag=${{ github.ref_name }}

  provider:
    needs: consumer
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - run: npm test -- --testPathPattern=pact/provider
        env:
          PACT_BROKER_BASE_URL: ${{ secrets.PACT_BROKER_URL }}
          PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
          PACT_PROVIDER_VERSION: ${{ github.sha }}
```

| CI Step            | Tool               | Artifact                         |
|--------------------|--------------------|----------------------------------|
| Consumer test      | vitest / jest      | `pacts/*.json`                   |
| Broker publish     | pact-broker CLI    | Pact stored in PactFlow          |
| Provider verify    | PactV3.verifyProvider | Pass/fail result posted back  |

## Mobile Consumer Contract

Mobile clients define contracts separately to catch field renames that the web consumer might tolerate:

```typescript
// mobile/tests/pact/track-detail.consumer.pact.ts
const provider = new PactV3({
  consumer: "example project-mobile",
  provider: "example project-workers-api",
  dir: path.resolve(__dirname, "../../pacts"),
});

it("returns track detail including artworkUrl", async () => {
  await provider
    .given("track 42 exists")
    .uponReceiving("GET /api/tracks/42")
    .withRequest({ method: "GET", path: "/api/tracks/42" })
    .willRespondWith({
      status: 200,
      body: like({
        id: 42,
        artworkUrl: string("https://cdn.example.com/art/42.jpg"), // mobile-specific
        bpm: integer(128),
      }),
    })
    .executeTest(async (mockServer) => {
      const detail = await fetchTrackDetail(mockServer.url, 42);
      expect(detail.artworkUrl).toBeTruthy();
    });
});
```

## Anti-patterns

- Putting provider-state logic inside the Worker itself (leaks test code into production bundle).
- Using `term()` regex matchers for URLs instead of `string()` — over-specifies and breaks on CDN changes.
- Running provider verification against the live deployed Worker (bypasses Miniflare isolation, leaks to prod D1).
- Publishing pacts without a version tag — makes can-i-deploy checks unreliable.
- Sharing one pact file across mobile and web consumers — hides mobile-specific field dependencies.

## Gotchas

- `PactV3.verifyProvider()` must resolve to a Promise; wrapping in `it()` without `return` silently passes.
- Miniflare 3.x requires `modules: true` for ESM Workers; omitting it produces an unhelpful "Worker not found" error.
- State handlers run in the test process, not inside the Worker — use the Miniflare binding APIs, not fetch, to mutate D1.
- PactFlow's can-i-deploy check respects environment tags; tag `main` and `production` differently or deploy gates fail spuriously.
- D1 binding name in Miniflare must exactly match the binding name in `wrangler.toml` or queries silently return empty.

## Verification

```bash
# Run consumer tests and inspect generated pact JSON
npm test -- --testPathPattern=pact/tracks.consumer
cat pacts/example project-pages-example project-workers-api.json | jq '.interactions | length'

# Verify provider locally against local pact files
PACT_BROKER_PUBLISH_VERIFICATION_RESULTS=false \
  npm test -- --testPathPattern=pact/provider

# Check can-i-deploy before releasing
npx pact-broker can-i-deploy \
  --pacticipant example project-workers-api \
  --version $(git rev-parse HEAD) \
  --to-environment production \
  --broker-base-url=$PACT_BROKER_URL \
  --broker-token=$PACT_BROKER_TOKEN
```

Expected output: `Computer says yes` with a matrix showing all consumer pacts verified green.

## Related

- `consumer-driven-contracts.md`
- `contract-testing-pact-patterns.md`
- `miniflare-d1-integration-testing.md`
- `d1-test-fixtures-wrangler-seed.md`
- `workers-test-patterns.md`

## Sources

- https://docs.pact.io/implementation_guides/javascript/docs/provider
- https://miniflare.dev/get-started/installation
- https://pactflow.io/docs/getting-started/
- https://developers.cloudflare.com/d1/reference/local-development/
