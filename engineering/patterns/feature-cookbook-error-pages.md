# feature-cookbook-error-pages

**Issue:** Error pages — 404, 500, friendly UX
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user hits `/api/users/missing`. The server returns
`{"error":"Not found"}`. The user sees a JSON blob. They
don't know what to do. They close the tab.

## Root cause
**Error pages are an afterthought.** They should be
designed, not generated.

**Source:** Various UX guides.

## The "404 page" pattern

For a not-found page:
```html
<!-- 404.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Page Not Found</title>
  <style>
    body {
      font-family: -apple-system, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #f5f5f5;
    }
    .container {
      text-align: center;
      padding: 2rem;
    }
    h1 { font-size: 6rem; margin: 0; color: #333; }
    p { color: #666; margin: 1rem 0; }
    a {
      color: #0066cc;
      text-decoration: none;
      padding: 0.5rem 1rem;
      border: 1px solid #0066cc;
      border-radius: 4px;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>404</h1>
    <p>The page you're looking for doesn't exist.</p>
    <a >Go home</a>
  </div>
</body>
</html>
```

The 404 page is friendly + helpful.

## The "500 page" pattern

For a server error:
```html
<!-- 500.html -->
<!DOCTYPE html>
<html>
<head>
  <title>Server Error</title>
  <!-- Same styling as 404 -->
</head>
<body>
  <div class="container">
    <h1>500</h1>
    <p>Something went wrong on our end. We've been notified.</p>
    <a >Try again</a>
  </div>
</body>
</html>
```

The 500 page is friendly + reassuring.

## The "maintenance page" pattern

For planned maintenance:
```html
<!-- maintenance.html -->
<!DOCTYPE html>
<html>
<head>
  <title>Scheduled Maintenance</title>
</head>
<body>
  <div class="container">
    <h1>🔧</h1>
    <p>We're doing some maintenance. We'll be back shortly.</p>
    <p>Status: <a href="https://status.example.com">status.example.com</a></p>
  </div>
</body>
</html>
```

The maintenance page is informative.

## The "API error response" pattern

For an API error:
```json
{
  "type": "https://example.com/probs/not-found",
  "title": "Not Found",
  "status": 404,
  "detail": "The user 'u_123' was not found",
  "code": "USER_NOT_FOUND"
}
```

The API error is structured + machine-readable.

## The "error page" generation

For CF Pages, use a Worker to generate error pages:
```ts
export const onRequest: PagesFunction = async (context) => {
  const response = await context.next();

  if (response.status === 404) {
    return new Response(getErrorPageHtml(404), {
      status: 404,
      headers: { 'content-type': 'text/html' },
    });
  }

  if (response.status === 500) {
    return new Response(getErrorPageHtml(500), {
      status: 500,
      headers: { 'content-type': 'text/html' },
    });
  }

  return response;
};

function getErrorPageHtml(status: number): string {
  return `<!DOCTYPE html>
<html>
<head><title>${status}</title></head>
<body>
  <h1>${status}</h1>
  <p>${getMessageForStatus(status)}</p>
  <a >Go home</a>
</body>
</html>`;
}

function getMessageForStatus(status: number): string {
  switch (status) {
    case 404: return "The page you're looking for doesn't exist.";
    case 500: return "Something went wrong on our end. We've been notified.";
    case 503: return "We're doing some maintenance. Please try again later.";
    default: return "An error occurred.";
  }
}
```

The error pages are generated.

## The "i18n error pages" pattern

For error pages in 20 locales:
```ts
function getErrorPageHtml(status: number, locale: string): string {
  const messages = {
    en: { 404: "The page doesn't exist.", 500: "Something went wrong." },
    es: { 404: "La página no existe.", 500: "Algo salió mal." },
    // ... 20 locales
  };

  return `<!DOCTYPE html>...<p>${messages[locale][status]}</p>...`;
}
```

The error messages are localized.

## The "client error page" pattern

For client-side errors (React error boundary):
```tsx
import { Component, ErrorInfo, ReactNode } from 'react';

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    logEvent('client.error', 'error', { error: String(error), info: String(info) });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-page">
          <h1>Something went wrong</h1>
          <p>We've been notified. Please try refreshing the page.</p>
          <button onClick={() => location.reload()}>Refresh</button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

The error boundary catches React errors.

## The "Sentry" pattern for client errors

For client error tracking:
```ts
import * as Sentry from '@sentry/browser';

Sentry.init({
  dsn: env.SENTRY_DSN,
  environment: env.ENVIRONMENT,
  release: env.RELEASE_VERSION,
});
```

The client errors are sent to Sentry.

## The "error page" design

For a good error page:
- ✅ Friendly message (not technical jargon)
- ✅ What the user can do (try again, contact support)
- ✅ A way to get back (home button, search)
- ✅ Branding (consistent with the rest of the site)
- ❌ Internal details (stack trace, error code)
- ❌ "Server error" without explanation

## The "status page" pattern

For a public status page:
```markdown
# Status

All systems operational.

## Recent incidents

- **2026-08-09 14:30 UTC** — Brief outage due to DB
  maintenance. Resolved in 15 minutes.
- **2026-08-08 09:00 UTC** — Slow search responses due to
  vendor issue. Resolved in 1 hour.
```

The status page is the public record.

## The "error page" anti-patterns

### 1. Default error page
- **Symptom:** User sees "Not Found" in plain text
- **Fix:** Custom error page

### 2. Internal details leaked
- **Symptom:** User sees "Error: ECONNREFUSED 127.0.0.1:5432"
- **Fix:** Strip internal details

### 3. No way to recover
- **Symptom:** User sees a blank page or error
- **Fix:** Home button + retry

### 4. Different error pages for different statuses
- **Symptom:** 404 is friendly; 500 is plain text
- **Fix:** Consistent design

### 5. No Sentry / no monitoring
- **Symptom:** Errors go unnoticed
- **Fix:** Log + alert

## Verification
- **Test:** 404 page is shown for missing pages
- **Test:** 500 page is shown for errors
- **Test:** Error pages are accessible
- **Live:** Errors are monitored

## Gotchas
- **The "default error page" anti-pattern.** A custom
  error page is part of the brand.
- **The "internal details in error" anti-pattern.** A
  stack trace in the response is a security issue.
- **The "no monitoring" anti-pattern.** Errors go
  unnoticed without monitoring.
- **The "no recovery" anti-pattern.** A user who can't
  recover leaves.

## Related
- `error-handling-strategies.md`
- `error-codes-and-messages.md`
- `api-design-best-practices.md`
- `safe-deploy-checklist.md`
- `incident-response.md`
