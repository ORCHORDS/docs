# Cloudflare Browser Rendering API — Puppeteer in Workers, Screenshots, PDF, AI Extraction

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application needs server-side screenshots, PDF generation, or
web scraping but you cannot run headless Chromium on your serverless
platform. You deploy a separate Node.js service with Puppeteer on a
VM, but it consumes 2 GB of RAM per browser instance and requires
manual scaling. Meanwhile, your AI agent pipeline needs to extract
structured data from rendered web pages, requiring both a browser
and an LLM in the same request flow.

## Context

Cloudflare Browser Rendering (now Browser Run) lets Workers drive
remote, Cloudflare-managed headless Chromium instances. GA since
mid-2025, it supports two integration modes: Workers Bindings
(full Puppeteer/Playwright API via `@cloudflare/puppeteer`) and a
REST API with Quick Actions (`/screenshot`, `/pdf`, `/markdown`,
`/json`, `/scrape`, `/links`). The `/json` endpoint integrates
Workers AI (Llama 3.3 70B by default) for structured data
extraction from rendered pages. Pricing is duration-based ($0.09
per browser-hour) with an additional concurrency charge ($2.00
per concurrent browser) for Workers Binding sessions.

## Workers Binding (Puppeteer)

```javascript
// src/index.js — screenshot with KV caching
import puppeteer from "@cloudflare/puppeteer";

export default {
  async fetch(request, env) {
    const { searchParams } = new URL(request.url);
    const url = searchParams.get("url");
    if (!url) {
      return new Response("Add ?url=https://example.com/");
    }

    const normalized = new URL(url).toString();
    let img = await env.BROWSER_KV.get(normalized, {
      type: "arrayBuffer",
    });

    if (img === null) {
      const browser = await puppeteer.launch(env.MYBROWSER);
      const page = await browser.newPage();
      await page.goto(normalized);
      img = await page.screenshot();
      await env.BROWSER_KV.put(normalized, img, {
        expirationTtl: 86400,
      });
      await browser.close();
    }

    return new Response(img, {
      headers: { "content-type": "image/jpeg" },
    });
  },
};
```

```toml
# wrangler.toml
name = "browser-worker"
main = "src/index.js"
compatibility_date = "2026-08-14"
compatibility_flags = ["nodejs_compat"]

[browser]
binding = "MYBROWSER"

[[kv_namespaces]]
binding = "BROWSER_KV"
id = "your-kv-namespace-id"
```

```
Workers Binding flow:

  1. Worker receives request
  2. puppeteer.launch(env.MYBROWSER) connects to managed Chromium
  3. Full Puppeteer API: goto, screenshot, pdf, evaluate, click
  4. Cache result in KV or R2
  5. browser.close() releases the session

  @cloudflare/puppeteer is a fork of Puppeteer trimmed for Workers.
  Most upstream APIs work, but local Chromium launch options do not.
```

## REST API Quick Actions

```
Endpoints (no Worker needed, token-authenticated):

  /screenshot   Capture PNG/JPEG screenshot
  /pdf          Generate PDF from rendered page
  /markdown     Extract page content as Markdown
  /json         AI-powered structured data extraction
  /content      Raw HTML after JavaScript rendering
  /scrape       CSS-selector-based element extraction
  /links        Extract all links from page
  /snapshot      Full page archive

Authentication:
  Authorization: Bearer <API_TOKEN>
  Content-Type: application/json
```

## AI-powered data extraction (/json)

```
The /json Quick Action renders a page, then passes content to
Workers AI for structured extraction.

Default model: @cf/meta/llama-3.3-70b-instruct-fp8-fast

Two extraction modes:
  1. Natural language prompt: "Extract product name and price"
  2. JSON schema: response_format with strict schema definition

Use case: AI agent pipelines that need web pages as structured
data for RAG or tool use.

REST only — billed on duration only (no concurrency charge).
```

## Pricing

```
                          REST API        Workers Bindings
─────────────────────────────────────────────────────────────
Duration charge:          $0.09/hr        $0.09/hr
Concurrency charge:       None            $2.00/concurrent browser
Billing granularity:      Rounds to hour  Rounds to hour

Free plan:
  10 minutes/day, 3 concurrent browsers

Workers Paid plan (included free):
  10 browser-hours/month
  10 concurrent browsers (monthly average)
  Then metered as above
```

## Anti-patterns

- **Not closing the browser** — `browser.close()` must be called
  to release the session. Idle open sessions leak concurrency
  billing since concurrency is metered separately from duration.
- **Uncached renders** — screenshots and PDFs are expensive to
  regenerate. Cache results in KV (small assets) or R2 (large
  PDFs) with appropriate TTLs.
- **Using Workers Bindings for simple captures** — if a single
  REST Quick Action (`/screenshot`, `/pdf`) suffices, using a full
  Puppeteer session adds the $2/concurrent-browser charge for no
  benefit.
- **Treating `@cloudflare/puppeteer` as upstream Puppeteer** — it
  is a fork with some APIs removed or modified. Test against the
  Cloudflare-specific API surface, not upstream documentation.

## Gotchas

- **Concurrency limits on free plan** — only 3 concurrent browsers.
  Under load, launch requests queue or fail. Design for sequential
  processing or upgrade to a paid plan.
- **Page load timeouts** — default navigation timeout may not
  suffice for JavaScript-heavy SPAs. Use `page.waitForSelector()`
  or `page.waitForNetworkIdle()` before capturing.
- **Workers CPU time limits** — the browser runs remotely but the
  Worker orchestrating it still has CPU time limits. Long-running
  Puppeteer scripts can hit the 30-second (free) or 15-minute
  (paid) wall clock limit.
- **AI extraction accuracy** — the `/json` endpoint uses an LLM,
  so extraction results are probabilistic. Validate output against
  the expected schema before using in downstream pipelines.

## Verification

- Browser binding configured in `wrangler.toml`.
- `browser.close()` called in all code paths (including error paths).
- Results cached in KV or R2 with appropriate TTLs.
- REST Quick Actions used for simple single-capture operations.
- AI extraction output validated against expected schema.
- Concurrency monitored against plan limits.

## Related

- `documentation/docs/policies/cloudflare/workers-ai-inference-gateway.md`
- `documentation/docs/policies/cloudflare/durable-objects-real-time-coordination.md`
- `documentation/docs/policies/performance/web-workers-sharedarraybuffer-parallelism.md`

## Source URLs (verified 2026-08-16)

- Browser Rendering API GA (Cloudflare Blog) — https://blog.cloudflare.com/browser-rendering-api-ga-rolling-out-cloudflare-snippets-swr-and-bringing-workers-for-platforms-to-our-paygo-plans/
- Browser Run Pricing — https://developers.cloudflare.com/browser-run/pricing/
- Cloudflare Puppeteer (GitHub) — https://github.com/cloudflare/puppeteer
- AI-Powered Structured Data Extraction — https://developers.cloudflare.com/browser-rendering/how-to/ai/
