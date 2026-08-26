# browser-run-best-practices

**Issue:** Browser Run (formerly Browser Rendering) — headless Chrome
**Date:** 2026-08-09
**Status:** documented

## Symptom
You need to take a screenshot of a webpage. You use
Puppeteer on your server. The server is in us-east-1.
Your user is in Asia. The screenshot takes 5s. You
wish you had a global browser.

## Root cause
**Headless Chrome is heavy + stateful.** Use Browser
Run at the edge.

**Source:** Browser Run docs:
https://developers.cloudflare.com/browser-run/

## The "Browser Run" concept

Browser Run (renamed from Browser Rendering in 2026):
- **Headless Chrome:** At the edge
- **Quick Actions:** Screenshot, PDF, markdown, etc.
- **Sessions:** Full Playwright/Puppeteer
- **CDP support:** Standard protocol
- **WebMCP:** Sites can declare tools for agents

**Source:** Browser Run rename:
https://developers.cloudflare.com/changelog/post/2026-04-15-br-rename/

## The "screenshot" pattern

For a screenshot via Quick Action:
```ts
const browser = env.BROWSER;

// Screenshot via Worker
const result = await browser.quickAction('screenshot', {
  url: 'https://example.com',
  viewport: { width: 1280, height: 720 },
  screenshotOptions: { type: 'png' },
});

return new Response(result.screenshot, {
  headers: { 'content-type': 'image/png' },
});
```

The screenshot is via Quick Action.

## The "PDF" pattern

For a PDF:
```ts
const result = await browser.quickAction('pdf', {
  url: 'https://example.com/invoice/123',
  pdfOptions: { format: 'A4', printBackground: true },
});

return new Response(result.pdf, {
  headers: { 'content-type': 'application/pdf' },
});
```

The PDF is generated.

## The "markdown" pattern

For markdown:
```ts
const result = await browser.quickAction('markdown', {
  url: 'https://example.com/article',
});

return new Response(result.markdown, {
  headers: { 'content-type': 'text/markdown' },
});
```

The HTML is converted to markdown.

## The "scrape" pattern

For scraping:
```ts
const result = await browser.quickAction('scrape', {
  url: 'https://example.com/products',
  elements: [
    { selector: '.product-title', attribute: 'text' },
    { selector: '.product-price', attribute: 'text' },
  ],
});
```

The data is extracted.

## The "Playwright" pattern

For full Playwright:
```ts
import { chromium } from '@cloudflare/playwright';

const browser = await chromium.launch(env.BROWSER);
const page = await browser.newPage();
await page.goto('https://example.com');
await page.screenshot({ path: 'screenshot.png' });
await browser.close();
```

The full Playwright API is available.

## The "Puppeteer" pattern

For Puppeteer:
```ts
import puppeteer from '@cloudflare/puppeteer';

const browser = await puppeteer.launch(env.BROWSER);
const page = await browser.newPage();
await page.goto('https://example.com');
const title = await page.title();
await browser.close();
```

The Puppeteer API is available.

**Source:** @cloudflare/puppeteer:
https://www.npmjs.com/package/@cloudflare/puppeteer

## The "crawl" pattern

For crawling:
```ts
const result = await fetch('https://api.browser.run/v1/crawl', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.BROWSER_API_TOKEN}` },
  body: JSON.stringify({
    url: 'https://example.com',
    maxDepth: 2,
    maxPages: 10,
  }),
});
```

The site is crawled.

## The "WebMCP" pattern

For WebMCP (sites declaring tools):
```ts
// The site has tools defined
// The agent discovers and calls them
const result = await browser.quickAction('use-tool', {
  url: 'https://example.com',
  tool: 'addToCart',
  args: { productId: 'p_123' },
});
```

WebMCP replaces screenshot-analyze-click loops.

## The "Live View" pattern

For debugging, see the browser live:
```ts
// Enable Live View
const session = await browser.newSession({
  live: { enabled: true },
});

// Or via dashboard
```

The session is live.

## The "Session Recordings" pattern

For recording a session:
```ts
const session = await browser.newSession({
  recording: { enabled: true },
});

await session.do('interact with the page', async (page) => {
  await page.click('button');
  await page.waitForNavigation();
});

// Replay the session
const replay = await browser.replaySession(session.id);
```

The session is recorded.

## The "Kitesurf" pattern (new 2026)

For AI agents, Kitesurf is a lightweight browser:
```ts
const session = await browser.newSession({
  browser: 'kitesurf',  // AI-optimized
});
```

Kitesurf uses 3-7x less CPU/memory.

## The "accessibility tree" pattern

For an accessibility tree (AI-friendly):
```ts
const result = await browser.quickAction('accessibilityTree', {
  url: 'https://example.com',
  options: { interestingOnly: true },
});
```

The accessibility tree is captured.

## The "Browser Run limits" pattern

For limits:
- **Concurrent browsers:** 120 per account (Paid)
- **New instances:** 1 per second (Paid)
- **REST API:** 10 req/sec
- **Free:** 10 min/day, 3 concurrent

The limits are checked.

## The "Browser Run pricing" pattern

For pricing:
- **REST API:** $0.09 / browser hour
- **Browser Sessions:** $0.09 / hour + $2 / concurrent
- **Free tier:** 10 min/day

The pricing is per usage.

## The "Browser Run anti-pattern" anti-patterns

### 1. Server-side Chrome
- **Issue:** Heavy + stateful
- **Fix:** Browser Run

### 2. No timeout
- **Issue:** Browser hangs
- **Fix:** Set timeout

### 3. Screenshot for everything
- **Issue:** Slow + large
- **Fix:** Use accessibilityTree or scrape

### 4. No concurrency limit
- **Issue:** Browser pool exhausted
- **Fix:** Queue

## Verification
- **Test:** Screenshot works
- **Test:** PDF works
- **Test:** Crawl works
- **Live:** Browser usage monitored
- **Audit:** Quarterly review

## Gotchas
- **The "server-side Chrome" anti-pattern.** Use
  Browser Run.
- **The "screenshot for everything" anti-pattern.** Use
  structured extraction.

## Related
- `cloudflare/workers-best-practices.md`
- `feature-cookbook-frontend.md`
- `feature-cookbook-monitoring.md`
- Browser Run: https://developers.cloudflare.com/browser-run/
- Playwright: https://playwright.dev/
- Puppeteer: https://pptr.dev/
