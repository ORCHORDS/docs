# Workers Custom Error Page Deploy Configuration

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

After deploying a Cloudflare Worker or Pages site, users encountering 4xx/5xx errors see
either the default Cloudflare "Ray ID" error page or a generic browser error. The goal is
to deploy custom branded error pages that are served consistently across all error
conditions, including Worker runtime crashes, upstream timeouts, and 404s for static assets,
without requiring a separate Workers deployment.

---

## Context

Cloudflare offers two distinct error-page mechanisms with different scopes and triggers:

| Mechanism | Scope | When it fires |
|---|---|---|
| **Cloudflare Custom Error Pages** (Zone-level) | DNS-proxied traffic | Cloudflare-generated errors (522, 524, 1xxx) |
| **Worker error handling** (`Response` with 4xx/5xx) | Worker script | Application errors within the Worker |
| **Pages `_not-found.html` / `404.html`** | Pages static assets | Missing static file paths |
| **Pages Functions error boundary** | Functions middleware | Uncaught errors in Functions |

Most production deployments need all four layers configured coherently so the user always
sees a branded error experience regardless of where the failure originates.

---

## Layer 1: Zone-Level Custom Error Pages (Cloudflare Dashboard + Terraform)

These are uploaded to Cloudflare and served when the edge itself generates an error (e.g.,
the origin is unreachable, a 1XXX Cloudflare error, or a 521 Connection Refused).

```typescript
// scripts/upload-error-pages.ts
import { readFileSync } from "node:fs";

interface ErrorPageUploadResult {
  success: boolean;
  errors: Array<{ code: number; message: string }>;
}

const ERROR_CODES = [401, 403, 404, 429, 500, 502, 503, 504] as const;
type ErrorCode = (typeof ERROR_CODES)[number];

const HTML_TEMPLATE = (code: number, message: string): string => `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Error ${code} - My App</title>
  <style>
    body { font-family: system-ui, sans-serif; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; margin: 0; background: #f8f8f8; }
    .card { background: white; padding: 2rem; border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,.1); text-align: center; max-width: 480px; }
    h1 { color: #e53e3e; font-size: 3rem; margin: 0 0 0.5rem; }
    p  { color: #4a5568; }
    a  { color: #3182ce; }
  </style>
</head>
<body>
  <div class="card">
    <h1>${code}</h1>
    <p>${message}</p>
    <p><a >Return to homepage</a></p>
  </div>
</body>
</html>`;

const ERROR_MESSAGES: Record<ErrorCode, string> = {
  401: "Authentication required.",
  403: "You do not have permission to access this page.",
  404: "The page you are looking for could not be found.",
  429: "Too many requests. Please wait a moment and try again.",
  500: "An internal server error occurred.",
  502: "Bad gateway. We are working on a fix.",
  503: "Service temporarily unavailable.",
  504: "Gateway timeout. Please try again.",
};

async function uploadErrorPage(
  zoneId: string,
  token: string,
  code: ErrorCode
): Promise<void> {
  const html = HTML_TEMPLATE(code, ERROR_MESSAGES[code]);
  const form = new FormData();
  form.append(
    "custom_error_response",
    new Blob([html], { type: "text/html" }),
    `${code}.html`
  );

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/custom_pages/${code}`,
    {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}` },
      body: form,
    }
  );

  const data = (await res.json()) as ErrorPageUploadResult;
  if (!data.success) {
    throw new Error(
      `Failed to upload ${code} page: ${data.errors.map((e) => e.message).join(", ")}`
    );
  }
  console.log(`Uploaded custom error page for ${code}`);
}

async function main(): Promise<void> {
  const zoneId = process.env.CLOUDFLARE_ZONE_ID ?? "";
  const token = process.env.CLOUDFLARE_API_TOKEN ?? "";

  if (!zoneId || !token) {
    throw new Error("CLOUDFLARE_ZONE_ID and CLOUDFLARE_API_TOKEN must be set");
  }

  for (const code of ERROR_CODES) {
    await uploadErrorPage(zoneId, token, code);
  }
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
```

---

## Layer 2: Worker Error Handler Middleware

Catch all unhandled errors within the Worker and return branded HTML responses.

```typescript
// src/middleware/error-handler.ts
export interface ErrorHandlerEnv {
  ENVIRONMENT: string;
}

export class AppError extends Error {
  constructor(
    message: string,
    public readonly statusCode: number = 500,
    public readonly userMessage: string = "An unexpected error occurred."
  ) {
    super(message);
    this.name = "AppError";
  }
}

function errorPageHtml(statusCode: number, message: string, debugInfo?: string): string {
  const isProduction = !debugInfo;
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Error ${statusCode}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f7f8fa; display: flex; align-items: center;
           justify-content: center; min-height: 100vh; padding: 1rem; }
    .card { background: #fff; border-radius: 12px; padding: 2.5rem;
            box-shadow: 0 4px 24px rgba(0,0,0,.08); max-width: 520px; width: 100%; }
    .status { font-size: 4rem; font-weight: 700; color: #e53935; line-height: 1; }
    .msg { margin-top: 1rem; color: #555; line-height: 1.6; }
    .home { display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.2rem;
            background: #1a73e8; color: white; border-radius: 6px;
            text-decoration: none; font-size: 0.9rem; }
    pre { margin-top: 1rem; background: #f0f0f0; padding: 1rem; border-radius: 6px;
          font-size: 0.75rem; overflow: auto; white-space: pre-wrap; }
  </style>
</head>
<body>
  <div class="card">
    <div class="status">${statusCode}</div>
    <p class="msg">${message}</p>
    ${!isProduction && debugInfo ? `<pre>${debugInfo}</pre>` : ""}
    <a class="home" >Back to Home</a>
  </div>
</body>
</html>`;
}

export function withErrorHandler<Env extends ErrorHandlerEnv>(
  handler: ExportedHandlerFetchHandler<Env>
): ExportedHandlerFetchHandler<Env> {
  return async (request, env, ctx): Promise<Response> => {
    try {
      return await handler(request, env, ctx);
    } catch (err) {
      const isProduction = env.ENVIRONMENT === "production";

      if (err instanceof AppError) {
        return new Response(
          errorPageHtml(err.statusCode, err.userMessage),
          {
            status: err.statusCode,
            headers: { "Content-Type": "text/html; charset=utf-8" },
          }
        );
      }

      const message = err instanceof Error ? err.message : String(err);
      const stack = err instanceof Error ? err.stack : undefined;

      console.error("Unhandled Worker error:", message, stack);

      return new Response(
        errorPageHtml(
          500,
          "An unexpected server error occurred. Our team has been notified.",
          isProduction ? undefined : stack
        ),
        {
          status: 500,
          headers: { "Content-Type": "text/html; charset=utf-8" },
        }
      );
    }
  };
}
```

Wire the middleware in `src/index.ts`:

```typescript
// src/index.ts
import { withErrorHandler, AppError } from "./middleware/error-handler";

interface Env {
  ENVIRONMENT: string;
  ASSETS: Fetcher;
}

const handler: ExportedHandlerFetchHandler<Env> = async (request, env) => {
  const url = new URL(request.url);

  if (url.pathname === "/api/data") {
    const data = await fetchData(); // may throw
    if (!data) throw new AppError("Resource not found", 404, "The requested data does not exist.");
    return Response.json(data);
  }

  // Serve static assets; return custom 404 if not found
  const assetResponse = await env.ASSETS.fetch(request);
  if (assetResponse.status === 404) {
    throw new AppError("Page not found", 404, "This page does not exist.");
  }
  return assetResponse;
};

export default { fetch: withErrorHandler(handler) };
```

---

## Layer 3: Pages Static 404 Page

For Pages projects, place a `404.html` at the root of the publish directory. Pages serves
this automatically for any unmatched static path.

```html
<!-- public/404.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>404 — Page Not Found</title>
  <link rel="stylesheet" >
</head>
<body>
  <main class="error-page">
    <h1>404</h1>
    <p>Page not found.</p>
    <a >Go home</a>
  </main>
</body>
</html>
```

---

## Layer 4: Pages Functions Error Boundary

```typescript
// functions/_middleware.ts
import type { PagesFunction } from "@cloudflare/workers-types";

const errorBoundary: PagesFunction = async (context) => {
  try {
    return await context.next();
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    const isProd = context.env.ENVIRONMENT === "production";

    const html = `<!DOCTYPE html>
<html><head><title>Error</title></head>
<body>
  <h1>Something went wrong</h1>
  ${!isProd ? `<pre>${message}</pre>` : ""}
  <a >Home</a>
</body></html>`;

    return new Response(html, {
      status: 500,
      headers: { "Content-Type": "text/html" },
    });
  }
};

export const onRequest = [errorBoundary];
```

---

## CI Deployment Workflow

```yaml
# .github/workflows/deploy-with-error-pages.yml
name: Deploy with Error Pages

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci
      - run: npm run build

      - name: Deploy Worker
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          command: deploy --env production

      - name: Upload zone-level custom error pages
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ZONE_ID: ${{ secrets.CLOUDFLARE_ZONE_ID }}
        run: npx tsx scripts/upload-error-pages.ts

  verify:
    needs: deploy
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Verify error pages are served
        env:
          BASE_URL: "https://api.example.com"
        run: |
          for path in "/nonexistent" "/api/does-not-exist"; do
            status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$path")
            ct=$(curl -sI "$BASE_URL$path" | grep -i content-type | tr -d '\r')
            echo "GET $path → $status | $ct"
            if [[ "$ct" != *"text/html"* ]]; then
              echo "ERROR: Expected HTML error page for $path, got: $ct"
              exit 1
            fi
          done
```

---

## Anti-patterns

- **Returning plain text or JSON for 4xx/5xx from a Worker** — browser error displays vary
  wildly across browsers when no HTML is returned. Always return `text/html` for errors
  served to end users.
- **Sending stack traces to production users** — leaks implementation details. Gate on the
  `ENVIRONMENT` binding.
- **Forgetting the zone-level custom error pages** — Worker error handlers do not fire for
  Cloudflare-generated errors (e.g., 522 origin timeout). Both layers are required.
- **Using `Response.error()` in a Worker** — this returns a network error, not a 500 HTML
  response. Always construct a `new Response(html, { status: 500 })` explicitly.
- **Embedding error HTML in every route handler** — centralise in a middleware wrapper
  (`withErrorHandler`) to avoid drift between error experiences across routes.

---

## Gotchas

- Zone-level custom error pages require a **Business or Enterprise plan** for some error
  codes (e.g., 1XXX Cloudflare errors). On Free/Pro, only 5xx pages are customisable.
- Custom error pages configured on the zone apply to ALL traffic through the zone, not just
  your Worker. If you have multiple Workers on a zone, they all share the same zone-level
  error pages.
- The `ASSETS` binding in a Worker returns a 404 `Response` object rather than throwing.
  Check `.status === 404` explicitly; do not rely on a thrown error.
- Pages `404.html` is served with a `404` status code automatically, but this does NOT
  trigger zone-level Cloudflare custom error pages — those only fire for Cloudflare-
  generated errors, not application-level 404s.
- `wrangler dev` does not simulate zone-level custom error pages. Test those with a deploy
  to a staging environment.

---

## Verification

```bash
# 1. Test Worker 404 handling
curl -sv https://api.example.com/does-not-exist 2>&1 | grep -E "< HTTP|content-type"

# 2. Test Worker 500 handling by hitting a route that throws
curl -sv https://api.example.com/api/trigger-error

# 3. Test Pages static 404.html
curl -sv https://my-site.pages.dev/no-such-page | head -5

# 4. Confirm zone-level custom error page for 503
curl -sv --resolve "example.com:443:203.0.113.1" https://example.com/

# 5. List current zone custom error pages via API
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/custom_pages" \
  -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" | jq '.result[] | {id, state}'
```

---

## Related

- `cloudflare-pages-functions-routing-rewrite-rules.md`
- `pages-functions-env-var-management.md`
- `workers-tail-worker-deploy-validation.md`
- `post-deploy-monitoring-checklist.md`
- `wrangler-tail-logs-deployment-verification.md`

---

## Sources

- Cloudflare Docs: Custom error pages — https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/
- Cloudflare Docs: Pages custom 404 — https://developers.cloudflare.com/pages/configuration/serving-pages/#not-found-behavior
- Cloudflare Docs: Pages Functions middleware — https://developers.cloudflare.com/pages/functions/middleware/
- Cloudflare Docs: Workers error handling — https://developers.cloudflare.com/workers/runtime-apis/response/
- Cloudflare API: Custom pages endpoint — https://developers.cloudflare.com/api/operations/custom-pages-for-a-zone-list-custom-pages
