# Playwright Workers Geo-Routing Country Simulation Testing

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker reads `request.cf.country` (or `cf.continent`, `cf.region`) to redirect
users, return localised content, block restricted regions, or select a nearby origin. Testing this
end-to-end—confirming the right redirect fires in the browser, the correct locale is served, or
the block page renders—requires injecting fake geo metadata into requests. In production Cloudflare
populates `cf.*` automatically; in local testing (`wrangler dev --local`) it is absent or defaults
to a hardcoded value, so tests must supply it explicitly. This article covers Playwright techniques
for simulating country-level geo-routing.

---

## Context

The `cf` object arrives on `Request.cf` inside a Worker. Its type is `IncomingRequestCfProperties`
from `@cloudflare/workers-types`. In `wrangler dev --local` (Miniflare v3), the `cf` object is
populated from a local stub and can be overridden by passing a `cf` property in `wrangler.toml`
or by sending a special header (`cf-connecting-ip`, `x-forwarded-for`, and the Miniflare-specific
`MF-CF-*` headers).

Key properties used in geo-routing:
- `cf.country` — ISO 3166-1 alpha-2 country code (e.g. `"DE"`, `"US"`, `"CN"`)
- `cf.continent` — `"EU"`, `"NA"`, `"AS"`, etc.
- `cf.region` — state/province string
- `cf.timezone` — IANA timezone string

---

## Geo Injection Strategy

Miniflare exposes CF properties via the `MF-CF-*` header family in local mode. Adding these
headers to Playwright requests—via `page.route` or browser extra HTTP headers—causes the Worker to
see the simulated `cf` values.

```
MF-CF-Country: DE
MF-CF-Continent: EU
MF-CF-Timezone: Europe/Berlin
```

> Note: These headers are stripped by `wrangler dev` in remote mode (actual Cloudflare edge). They
> only work with `wrangler dev --local` / Miniflare. For remote dev testing, use an alternative
> approach described in the "Testing Against a Remote Worker" section below.

---

## Playwright Config

```ts
// playwright.config.ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://localhost:8787",
  },
  webServer: {
    command: "wrangler dev --local --port 8787",
    url: "http://localhost:8787/health",
    reuseExistingServer: !process.env.CI,
    timeout: 20_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
```

---

## Fixture: Country Context Injection

```ts
// tests/fixtures.ts
import { test as base, type Page } from "@playwright/test";

type GeoFixtures = {
  countryPage: (country: string, continent?: string, timezone?: string) => Promise<Page>;
};

export const test = base.extend<GeoFixtures>({
  countryPage: async ({ browser }, use) => {
    const pages: Page[] = [];

    const factory = async (
      country: string,
      continent = "EU",
      timezone = "Europe/London"
    ): Promise<Page> => {
      const context = await browser.newContext();
      const page = await context.newPage();

      // Inject CF geo headers for every request this page makes
      await page.route("**/*", (route) => {
        const headers = {
          ...route.request().headers(),
          "MF-CF-Country": country,
          "MF-CF-Continent": continent,
          "MF-CF-Timezone": timezone,
        };
        route.continue({ headers });
      });

      pages.push(page);
      return page;
    };

    await use(factory);

    for (const p of pages) await p.close();
  },
});

export { expect } from "@playwright/test";
```

---

## Testing Country-Based Redirects

```ts
// tests/geo-routing.spec.ts
import { test, expect } from "./fixtures";

test.describe("country redirects", () => {
  test("redirects DE users to /de/ locale", async ({ countryPage }) => {
    const page = await countryPage("DE", "EU", "Europe/Berlin");

    const response = await page.goto("/");

    // Worker should redirect to /de/
    expect(page.url()).toMatch(/\/de\//);
    expect(response?.status()).toBe(200); // after redirect chain
  });

  test("redirects US users to /en-us/ locale", async ({ countryPage }) => {
    const page = await countryPage("US", "NA", "America/New_York");
    await page.goto("/");
    expect(page.url()).toMatch(/\/en-us\//);
  });

  test("serves default locale for unknown country code", async ({ countryPage }) => {
    const page = await countryPage("XX", "EU", "UTC");
    await page.goto("/");
    expect(page.url()).toMatch(/\/en\//);
  });
});
```

---

## Testing Geo-Based Content Localisation

```ts
test.describe("localised content", () => {
  test("renders German currency symbol for DE users", async ({ countryPage }) => {
    const page = await countryPage("DE", "EU", "Europe/Berlin");
    await page.goto("/pricing");

    const priceElement = page.locator('[data-testid="price"]').first();
    await expect(priceElement).toBeVisible();
    await expect(priceElement).toContainText("€");
  });

  test("renders USD for US users", async ({ countryPage }) => {
    const page = await countryPage("US", "NA", "America/New_York");
    await page.goto("/pricing");

    const priceElement = page.locator('[data-testid="price"]').first();
    await expect(priceElement).toContainText("$");
  });

  test("renders correct language tag in html[lang]", async ({ countryPage }) => {
    const page = await countryPage("FR", "EU", "Europe/Paris");
    await page.goto("/");

    const htmlLang = await page.locator("html").getAttribute("lang");
    expect(htmlLang).toMatch(/^fr/);
  });
});
```

---

## Testing Geo-Based Access Restrictions

```ts
test.describe("geo-blocked regions", () => {
  test("renders block page for restricted country CN", async ({ countryPage }) => {
    const page = await countryPage("CN", "AS", "Asia/Shanghai");

    const response = await page.goto("/app");

    expect(response?.status()).toBe(451); // Unavailable For Legal Reasons
    await expect(page.locator('[data-testid="geo-block-message"]')).toBeVisible();
    await expect(page.locator('[data-testid="geo-block-message"]')).toContainText(
      /not available in your region/i
    );
  });

  test("allows access from unrestricted country US", async ({ countryPage }) => {
    const page = await countryPage("US", "NA", "America/Chicago");
    const response = await page.goto("/app");
    expect(response?.status()).toBe(200);
    await expect(page.locator('[data-testid="geo-block-message"]')).not.toBeVisible();
  });
});
```

---

## Inspecting the `cf` Object via a Debug Endpoint

Add a `/__cf-debug` Worker route (test environments only) to assert what the Worker actually sees:

```ts
test("Worker receives correct cf.country value", async ({ request }) => {
  const res = await request.get("http://localhost:8787/__cf-debug", {
    headers: {
      "MF-CF-Country": "JP",
      "MF-CF-Continent": "AS",
      "MF-CF-Timezone": "Asia/Tokyo",
    },
  });

  expect(res.status()).toBe(200);
  const cf = await res.json();
  expect(cf.country).toBe("JP");
  expect(cf.continent).toBe("AS");
  expect(cf.timezone).toBe("Asia/Tokyo");
});
```

The debug Worker route:
```ts
// src/worker.ts (test-only route, guarded by env var)
if (url.pathname === "/__cf-debug" && env.ENVIRONMENT === "test") {
  return Response.json({
    country: request.cf?.country,
    continent: request.cf?.continent,
    timezone: request.cf?.timezone,
  });
}
```

---

## Testing Against a Remote Worker (Staging)

When running Playwright against a remote `wrangler dev --remote` or a deployed Workers preview,
`MF-CF-*` headers are stripped at the Cloudflare edge. Use a Worker-level escape hatch:

```ts
// Staging-only: read country from X-Test-Country header when ENVIRONMENT=staging
const country =
  env.ENVIRONMENT === "staging"
    ? (request.headers.get("X-Test-Country") ?? request.cf?.country)
    : request.cf?.country;
```

In Playwright, send `X-Test-Country` instead of `MF-CF-Country` for remote targets:

```ts
await page.route("**/*", (route) => {
  route.continue({
    headers: {
      ...route.request().headers(),
      "X-Test-Country": "DE",
    },
  });
});
```

---

## Anti-patterns

- **Setting `extraHTTPHeaders` at the context level without `page.route`** — Playwright's
  `extraHTTPHeaders` does not override existing headers that the browser sends. Use `page.route`
  to merge headers correctly.
- **Hardcoding geo headers in `playwright.config.ts` globally** — geo tests require per-test
  country variation; a global header forces all tests into one country.
- **Forgetting to close browser contexts created in the fixture** — each `countryPage` call creates
  a new context; ensure cleanup runs even when tests fail.
- **Testing redirect chains without checking the final URL** — `page.goto` follows redirects by
  default; check `page.url()` not `response.url()` to assert the resolved destination.

---

## Gotchas

- `MF-CF-*` headers are Miniflare-specific and undocumented. They may change in future Miniflare
  releases; pin the `wrangler` version in CI.
- Miniflare populates a default `cf` stub (usually `country: "US"`) when no header is provided.
  Tests that expect the absence of geo data must explicitly set an empty or sentinel value.
- Playwright `page.route` fires for all resource types including images and fonts. Add a
  `resourceType` filter to avoid unnecessary header injection overhead:
  ```ts
  await page.route("**/*", (route) => {
    if (["document", "fetch", "xhr"].includes(route.request().resourceType())) {
      route.continue({ headers: { ...route.request().headers(), "MF-CF-Country": "DE" } });
    } else {
      route.continue();
    }
  });
  ```
- Country codes are case-sensitive in `cf.country`; always use uppercase ISO codes.

---

## Verification

```bash
# Run geo-routing tests
npx playwright test tests/geo-routing.spec.ts

# Run for a specific country scenario
npx playwright test tests/geo-routing.spec.ts --grep "DE users"

# Debug with trace to inspect headers sent
npx playwright test tests/geo-routing.spec.ts --trace on
```

---

## Related

- `vitest-workers-geolocation-cf-object-mocking.md`
- `playwright-workers-api-contract-e2e-testing.md`
- `playwright-workers-feature-flag-ab-test.md`
- `playwright-network-interception.md`

---

## Sources

- Cloudflare Workers `Request.cf` properties — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Miniflare CF overrides — https://miniflare.dev/core/fetch#cloudflare-properties
- Playwright `page.route` — https://playwright.dev/docs/network#modify-requests
- ISO 3166-1 alpha-2 country codes — https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2
