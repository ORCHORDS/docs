# Playwright Workers Infinite Scroll D1 Keyset E2E

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your app uses a Cloudflare Worker + D1 backend to serve paginated content via keyset (cursor) pagination, and a front-end that triggers the next page when the user scrolls to the bottom (infinite scroll). E2E tests that use `page.keyboard.press("End")` or fixed `scrollTo` coordinates are brittle across viewport sizes, and tests that only assert the final DOM state miss scroll-trigger timing bugs. You need a robust Playwright approach that controls scroll events explicitly, waits for the Worker's D1 query responses, and asserts cursor state across multiple page loads.

## Context

Keyset pagination with D1 looks like:

```sql
SELECT * FROM posts
WHERE (created_at, id) < (:cursor_ts, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

The Worker returns `{ items: [...], nextCursor: "base64-encoded-ts:id" | null }`. The front-end stores `nextCursor` in component state, sends it on the next scroll event, and stops triggering when `nextCursor` is null.

Testing challenges:
- The sentinel element (the element the scroll observer watches) must be visible in the viewport — not just exist in the DOM.
- Network timing: the Worker's D1 query completes asynchronously; the UI must show a loading state before and items after.
- Cursor correctness: the cursor in page N must exactly match the last item on page N's response.
- Empty state: when all items are loaded, the sentinel is removed and no further fetches happen.

## 1. Worker: Keyset Pagination Endpoint

```typescript
// src/worker.ts
export interface Env {
  DB: D1Database;
}

interface Post {
  id: string;
  title: string;
  created_at: string;
}

function encodeCursor(post: Post): string {
  return btoa(`${post.created_at}:${post.id}`);
}

function decodeCursor(cursor: string): { ts: string; id: string } {
  const raw = atob(cursor);
  const colonIdx = raw.indexOf(":");
  return { ts: raw.slice(0, colonIdx), id: raw.slice(colonIdx + 1) };
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname !== "/api/posts") return new Response("Not Found", { status: 404 });

    const cursorParam = url.searchParams.get("cursor");
    const limit = Math.min(Number(url.searchParams.get("limit") ?? "20"), 100);

    let rows: Post[];
    if (cursorParam) {
      const { ts, id } = decodeCursor(cursorParam);
      const result = await env.DB.prepare(
        `SELECT id, title, created_at FROM posts
         WHERE (created_at < ? OR (created_at = ? AND id < ?))
         ORDER BY created_at DESC, id DESC LIMIT ?`
      )
        .bind(ts, ts, id, limit)
        .all<Post>();
      rows = result.results;
    } else {
      const result = await env.DB.prepare(
        `SELECT id, title, created_at FROM posts ORDER BY created_at DESC, id DESC LIMIT ?`
      )
        .bind(limit)
        .all<Post>();
      rows = result.results;
    }

    const nextCursor =
      rows.length === limit ? encodeCursor(rows[rows.length - 1]) : null;

    return Response.json({ items: rows, nextCursor });
  },
};
```

## 2. Front-End: Intersection Observer Infinite Scroll

```html
<!-- public/index.html (served via Workers Assets) -->
<div id="feed"></div>
<div id="sentinel" data-testid="scroll-sentinel"></div>
<div id="loading" data-testid="loading-indicator" hidden>Loading…</div>
<div id="end-of-feed" data-testid="end-of-feed" hidden>All caught up!</div>

<script type="module">
  let cursor = null;
  let loading = false;

  async function fetchPage() {
    if (loading) return;
    loading = true;
    document.getElementById("loading").hidden = false;

    const url = new URL("/api/posts", location.href);
    url.searchParams.set("limit", "20");
    if (cursor) url.searchParams.set("cursor", cursor);

    const res = await fetch(url);
    const { items, nextCursor } = await res.json();

    const feed = document.getElementById("feed");
    for (const post of items) {
      const el = document.createElement("article");
      el.dataset.postId = post.id;
      el.textContent = post.title;
      feed.appendChild(el);
    }

    cursor = nextCursor;
    document.getElementById("loading").hidden = true;
    loading = false;

    if (!cursor) {
      document.getElementById("sentinel").remove();
      document.getElementById("end-of-feed").hidden = false;
    }
  }

  const sentinel = document.getElementById("sentinel");
  const observer = new IntersectionObserver(
    (entries) => { if (entries[0].isIntersecting) fetchPage(); },
    { threshold: 0.1 }
  );
  observer.observe(sentinel);

  // Load the first page on mount
  fetchPage();
</script>
```

## 3. Playwright Config and D1 Seed Fixture

```typescript
// playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  use: {
    baseURL: "http://localhost:8788",
    viewport: { width: 1280, height: 800 },
  },
  globalSetup: "./tests/global-setup.ts",
  testDir: "./tests",
});
```

```typescript
// tests/global-setup.ts
import { execSync } from "child_process";

export default async function globalSetup() {
  // Seed 50 posts so there are at least 3 pages of 20 items
  execSync("npx tsx tests/seed-d1.ts", { stdio: "inherit" });
}
```

```typescript
// tests/seed-d1.ts
import { execSync } from "child_process";

const posts = Array.from({ length: 50 }, (_, i) => {
  const ts = new Date(Date.now() - i * 60_000).toISOString();
  const id = `post-${String(i).padStart(3, "0")}`;
  return `('${id}', 'Post ${i + 1}', '${ts}')`;
});

const sql = `
  DELETE FROM posts;
  INSERT INTO posts (id, title, created_at) VALUES ${posts.join(",")};
`;

execSync(`echo "${sql}" | npx wrangler d1 execute local-db --local --command "${sql}"`, {
  stdio: "inherit",
});
```

## 4. Core Infinite Scroll E2E Test

```typescript
// tests/infinite-scroll.spec.ts
import { test, expect, Page } from "@playwright/test";

async function scrollSentinelIntoView(page: Page) {
  const sentinel = page.getByTestId("scroll-sentinel");
  // Use scrollIntoView to guarantee the sentinel is visible to the IntersectionObserver
  await sentinel.scrollIntoViewIfNeeded();
}

async function waitForPageLoad(page: Page, expectedCount: number) {
  // Wait until the feed has exactly `expectedCount` articles
  await expect(page.locator("article")).toHaveCount(expectedCount, { timeout: 10_000 });
}

test("loads first page on initial render", async ({ page }) => {
  await page.goto("/");
  await waitForPageLoad(page, 20);
  // Loading indicator is gone
  await expect(page.getByTestId("loading-indicator")).toBeHidden();
  // Sentinel still present — more pages available
  await expect(page.getByTestId("scroll-sentinel")).toBeVisible();
});

test("loads second page when sentinel scrolls into view", async ({ page }) => {
  await page.goto("/");
  await waitForPageLoad(page, 20);

  await scrollSentinelIntoView(page);
  await waitForPageLoad(page, 40);

  // Cursor in the second fetch URL must match last item of page 1
  // (intercepted via Playwright network interception)
});

test("shows end-of-feed after last page", async ({ page }) => {
  await page.goto("/");
  await waitForPageLoad(page, 20);

  await scrollSentinelIntoView(page);
  await waitForPageLoad(page, 40);

  await scrollSentinelIntoView(page);
  await waitForPageLoad(page, 50); // 50 total seeded posts

  await expect(page.getByTestId("end-of-feed")).toBeVisible();
  await expect(page.getByTestId("scroll-sentinel")).toHaveCount(0);
});
```

## 5. Cursor Correctness via Network Interception

```typescript
test("cursor in page-2 request matches last item of page-1 response", async ({ page }) => {
  let page1Response: { items: { id: string; created_at: string }[]; nextCursor: string };
  let page2CursorParam: string | null = null;

  // Intercept /api/posts calls
  page.on("response", async (res) => {
    if (res.url().includes("/api/posts")) {
      const url = new URL(res.url());
      const cursor = url.searchParams.get("cursor");
      if (!cursor) {
        page1Response = await res.json();
      } else {
        page2CursorParam = cursor;
      }
    }
  });

  await page.goto("/");
  await waitForPageLoad(page, 20);
  await scrollSentinelIntoView(page);
  await waitForPageLoad(page, 40);

  // The cursor sent in the page-2 request must equal the cursor from page-1 response
  expect(page2CursorParam).toBe(page1Response!.nextCursor);

  // Decode the cursor and verify it matches the last item
  const decoded = atob(page2CursorParam!);
  const [cursorTs, cursorId] = decoded.split(":");
  const lastItem = page1Response!.items[page1Response!.items.length - 1];
  expect(cursorTs).toBe(lastItem.created_at);
  expect(cursorId).toBe(lastItem.id);
});
```

## 6. No Duplicate Fetches When Sentinel Bounces

```typescript
test("does not fetch twice if sentinel re-enters viewport before first response", async ({ page }) => {
  const fetchCalls: string[] = [];

  await page.route("/api/posts**", async (route) => {
    fetchCalls.push(route.request().url());
    // Slow response to increase window for double-trigger
    await new Promise((r) => setTimeout(r, 200));
    await route.continue();
  });

  await page.goto("/");
  await waitForPageLoad(page, 20);

  // Rapidly scroll down and up — sentinel enters viewport twice quickly
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));

  await waitForPageLoad(page, 40);

  // Only 2 total calls: page 1 (initial) + page 2 (one trigger, not two)
  const page2Calls = fetchCalls.filter((u) => u.includes("cursor="));
  expect(page2Calls).toHaveLength(1);
});
```

## Anti-patterns

- **Using `page.keyboard.press("End")` to trigger scroll**: This sends a keyboard event, not a scroll event, and does not move the viewport in a way the IntersectionObserver detects.
- **Asserting `page.locator("article").count() > 20`**: This passes even if items are duplicated. Use `.toHaveCount(exact)` with the expected total.
- **Seeding with fewer items than one full page**: Tests for second-page behaviour never trigger because `nextCursor` is null after the first fetch.
- **Using `page.waitForTimeout()` between scroll and assertion**: Replace with `expect(locator).toHaveCount()` which polls automatically.
- **Resetting D1 state inside individual tests without a transaction**: Concurrent Playwright workers corrupt shared D1 data. Use `--workers=1` for D1-backed tests or partition data by test via unique prefixes.

## Gotchas

- `scrollIntoViewIfNeeded()` uses the browser's native scroll, which respects `scroll-behavior: smooth`. In tests, smooth scroll can delay IntersectionObserver callbacks. Disable it in the test environment: `await page.addStyleTag({ content: '* { scroll-behavior: auto !important; }' })`.
- The IntersectionObserver fires asynchronously after the scroll. If `waitForPageLoad` times out, add a `page.waitForResponse('/api/posts')` step before the count assertion to ensure the network response was actually received.
- Wrangler's local D1 uses SQLite under `~/.wrangler/state`. Concurrent test runs that share the same SQLite file will deadlock. Use `--persist-to` with a unique temp directory per worker.
- Playwright's `page.on("response")` fires for all responses including assets. Filter by URL carefully to avoid false cursor readings.

## Verification

```bash
# Start the Worker in local mode
npx wrangler dev --local --persist-to /tmp/wrangler-test-state &

# Run the infinite scroll suite
npx playwright test tests/infinite-scroll.spec.ts --reporter=list

# With tracing enabled to debug scroll timing
npx playwright test tests/infinite-scroll.spec.ts --trace=on
npx playwright show-trace test-results/**/trace.zip
```

## Related

- `playwright-d1-state-reset-between-tests.md` — resetting D1 between tests without race conditions
- `playwright-workers-r2-file-upload-e2e.md` — other Workers + Playwright integration patterns
- `d1-test-fixtures-wrangler-seed.md` — seeding D1 for local test runs

## Sources

- IntersectionObserver API: https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API
- Playwright scrollIntoViewIfNeeded: https://playwright.dev/docs/api/class-locator#locator-scroll-into-view-if-needed
- Cloudflare D1 local development: https://developers.cloudflare.com/d1/local-development/
- Keyset pagination: https://use-the-index-luke.com/no-offset
