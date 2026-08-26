# Deploy Gate: E2E Tests with Playwright on Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A Cloudflare Pages deployment passes build + lint but ships a broken UI because
no automated browser test ran against the actual preview URL before production
promotion. Regressions in auth flows, mobile layouts, and API-wired components
are caught only after users report them.

## Context

example project (example.com) deploys its front-end via Cloudflare Pages. Every push to a
feature branch creates a Pages preview deployment at a unique URL like
`https://abc123.example project-app.pages.dev`. This article describes using Playwright
as a deploy gate in GitHub Actions: extract the preview URL, run smoke tests
against it (including mobile viewport), and block merging if tests fail.

---

## Pages Preview URL Extraction

Cloudflare does not natively expose the preview URL as a GitHub Actions output.
Two reliable methods:

### Method A — Wrangler Pages Deploy Output Parsing

```yaml
# .github/workflows/deploy-gate.yml (excerpt)
- name: Deploy to Pages
  id: pages_deploy
  run: |
    OUTPUT=$(wrangler pages deploy dist \
      --project-name example project-app \
      --branch "${{ github.head_ref }}" \
      2>&1)
    echo "$OUTPUT"
    URL=$(echo "$OUTPUT" | grep -oP 'https://[a-z0-9\-]+\.example project-app\.pages\.dev' | head -1)
    echo "preview_url=$URL" >> "$GITHUB_OUTPUT"
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

### Method B — Cloudflare Pages API Poll

```bash
#!/usr/bin/env bash
# scripts/get-preview-url.sh
ACCOUNT_ID=$1
PROJECT=$2
BRANCH=$3
TOKEN=$4

for i in $(seq 1 20); do
  RESP=$(curl -s \
    -H "Authorization: Bearer $TOKEN" \
    "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/$PROJECT/deployments?branch=$BRANCH&per_page=1")

  STATUS=$(echo "$RESP" | jq -r '.result[0].latest_stage.status')
  URL=$(echo "$RESP" | jq -r '.result[0].url')

  if [[ "$STATUS" == "success" ]]; then
    echo "$URL"
    exit 0
  fi
  sleep 15
done

echo "Timed out waiting for Pages deployment" >&2
exit 1
```

---

## Playwright Smoke Test Suite

Keep the gate suite small and fast (< 2 min). Each test verifies a critical
user path, not every component.

```typescript
// tests/smoke/deploy-gate.spec.ts
import { test, expect, devices } from "@playwright/test";

const BASE = process.env.PREVIEW_URL!;

test.describe("deploy gate — desktop", () => {
  test("home page loads and shows nav", async ({ page }) => {
    await page.goto(BASE);
    await expect(page.locator("nav")).toBeVisible();
    await expect(page).toHaveTitle(/example project/);
  });

  test("login page reachable", async ({ page }) => {
    await page.goto(`${BASE}/login`);
    await expect(page.locator('input[type="email"]')).toBeVisible();
  });

  test("health API endpoint returns 200", async ({ request }) => {
    const resp = await request.get(`${BASE}/api/health`);
    expect(resp.status()).toBe(200);
  });
});

test.describe("deploy gate — mobile", () => {
  test.use({ ...devices["iPhone 15"] });

  test("home page renders mobile nav", async ({ page }) => {
    await page.goto(BASE);
    await expect(page.locator('[data-testid="mobile-menu-btn"]')).toBeVisible();
  });

  test("login form is scrollable without overflow on small viewport", async ({
    page,
  }) => {
    await page.goto(`${BASE}/login`);
    const bodyWidth = await page.evaluate(() => document.body.scrollWidth);
    const viewportWidth = page.viewportSize()!.width;
    expect(bodyWidth).toBeLessThanOrEqual(viewportWidth + 1);
  });
});
```

### Playwright Config for Preview URLs

```typescript
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests/smoke",
  timeout: 30_000,
  retries: 1,
  workers: 2,
  reporter: [["github"], ["html", { outputFolder: "pw-report", open: "never" }]],
  use: {
    baseURL: process.env.PREVIEW_URL,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium" },
    { name: "firefox" },
    { name: "Mobile Chrome", use: { ...require("@playwright/test").devices["Pixel 7"] } },
  ],
});
```

---

## GitHub Actions Gate Step

```yaml
# .github/workflows/deploy-gate.yml
name: Deploy Gate

on:
  pull_request:
    branches: [main]

jobs:
  deploy-and-test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write     # for posting test summary as PR comment
      statuses: write

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - run: pnpm build

      - name: Deploy preview
        id: deploy
        run: |
          URL=$(wrangler pages deploy dist \
            --project-name example project-app \
            --branch "${{ github.head_ref }}" \
            2>&1 | grep -oP 'https://[a-z0-9\-]+\.example project-app\.pages\.dev' | head -1)
          echo "preview_url=$URL" >> "$GITHUB_OUTPUT"
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Install Playwright browsers
        run: pnpm exec playwright install --with-deps chromium firefox

      - name: Run smoke tests
        id: smoke
        run: pnpm exec playwright test
        env:
          PREVIEW_URL: ${{ steps.deploy.outputs.preview_url }}

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: pw-report/

      - name: Post summary to PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const url = "${{ steps.deploy.outputs.preview_url }}";
            const pass = "${{ steps.smoke.outcome }}" === "success";
            const icon = pass ? "✅" : "❌";
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `${icon} Deploy gate: preview at ${url}\nSmoke tests: **${pass ? "passed" : "FAILED"}**`,
            });
```

### Gate Enforcement Table

| Condition                        | Action                                 |
|----------------------------------|----------------------------------------|
| Smoke tests pass                 | PR check green; merge allowed          |
| Smoke tests fail (flake)         | 1 automatic retry; fail hard if still failing |
| Preview deploy times out         | Fail gate; do not merge                |
| `PREVIEW_URL` not extracted      | Fail gate with explicit error message  |
| Mobile overflow test fails       | Block merge; alert `#design` channel   |

---

## Mobile Viewport Test Details

Mobile-specific assertions catch layout regressions that only appear on narrow
viewports. Two high-value checks:

```typescript
// Horizontal overflow detector — no element should force horizontal scroll
test("no horizontal overflow on any page", async ({ page }) => {
  const paths = ["/", "/login", "/dashboard", "/settings"];
  for (const path of paths) {
    await page.goto(`${BASE}${path}`);
    const overflow = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("*")).some(
        (el) => el.scrollWidth > document.documentElement.clientWidth
      );
    });
    expect(overflow, `Overflow on ${path}`).toBe(false);
  }
});

// Touch target size check (WCAG 2.5.5 — 44x44 px minimum)
test("primary CTA meets touch target size", async ({ page }) => {
  await page.goto(BASE);
  const btn = page.locator('[data-testid="cta-primary"]');
  const box = await btn.boundingBox();
  expect(box?.width).toBeGreaterThanOrEqual(44);
  expect(box?.height).toBeGreaterThanOrEqual(44);
});
```

---

## Anti-patterns

- **Running E2E against `localhost` in CI** — the gate must test the actual
  deployed preview; local builds may differ from the Cloudflare edge environment.
- **Using a single `chromium`-only project** — mobile regressions are invisible
  without a mobile device profile.
- **Hardcoding the preview URL** — the URL changes per deployment; extract it
  dynamically from Wrangler output or the Pages API.
- **Running the full regression suite as a gate** — suites > 10 min cause
  developers to bypass the gate. Keep the smoke suite under 2 minutes.
- **Not retrying flaky tests** — network latency to the edge can cause
  intermittent failures; set `retries: 1` in `playwright.config.ts`.

---

## Gotchas

- Cloudflare Pages preview URLs are only accessible after the deployment status
  reaches `success`. Poll the API before running Playwright.
- Pages preview deployments are served over HTTPS with a Cloudflare-issued cert.
  Playwright trusts system CAs; no `ignoreHTTPSErrors` needed.
- The `CLOUDFLARE_API_TOKEN` must have `Cloudflare Pages:Edit` permission on the
  account. A zone-scoped token is insufficient.
- PR branches with slashes (`feat/foo`) are URL-encoded in the Pages subdomain.
  The deployment URL uses the branch alias, not the raw branch name.

---

## Verification

```bash
# Run smoke tests locally against a specific preview
PREVIEW_URL=https://abc123.example project-app.pages.dev \
  pnpm exec playwright test --project=chromium --headed

# Confirm Pages API returns deployment status
curl -s \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/pages/projects/example project-app/deployments?per_page=1" \
  | jq '.result[0] | {url, status: .latest_stage.status}'
```

---

## Related

- `cloudflare-pages-preview-deployments.md`
- `deploy-gate-antipatterns.md`
- `deployment-verification-smoke-tests.md`
- `wrangler-deploy-github-actions-workers.md`
- `consumer-contract-deploy-gates.md`

## Sources

- Playwright docs — https://playwright.dev/docs/intro
- Cloudflare Pages deployments API — https://developers.cloudflare.com/api/operations/cloudflare-pages-get-deployments
- GitHub Actions: using outputs between steps — https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#setting-an-output-parameter
- WCAG 2.5.5 Target Size — https://www.w3.org/WAI/WCAG21/Understanding/target-size.html
