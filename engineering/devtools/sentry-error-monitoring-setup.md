# Sentry / Error Monitoring Integration for Dev & Staging

> Wiring Sentry (or equivalent error monitors — LogRocket, Rollbar, Bugsnag)
> so that runtime errors are captured with full stack traces, breadcrumbs, and
> repro context — without leaking PII or breaking the dev workflow.

---

## When to use this

- Production errors arrive with no stack trace or wrong line numbers.
- A bug reproduces on staging but you have no idea what the user did before it.
- You're shipping minified/bundled JS and the trace points to `a.min.js:1:4521`.
- You need to decide what to capture in dev vs staging vs prod.

## Symptom

An error is thrown in production. The user sees a blank screen or a 500.
You get a Sentry alert with:

```
TypeError: Cannot read properties of undefined (reading 'map')
  at a.min.js:1:4521
```

No useful file, no useful line, no breadcrumbs. You're flying blind.

## Step-by-step setup

### 1. Install the SDK for your stack

```bash
# Node backend
pnpm add @sentry/node

# Browser frontend (Next.js, Vite, React, Vue)
pnpm add @sentry/browser

# Capacitor / React Native — use @sentry/capacitor or @sentry/react-native
pnpm add @sentry/capacitor
```

### 2. Initialize as early as possible

```js
// Node — first line of app entry, before other imports
const Sentry = require('@sentry/node');
Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.NODE_ENV,   // dev | staging | prod
  tracesSampleRate: process.env.NODE_ENV === 'production' ? 0.2 : 1.0,
  profilesSampleRate: 0.1,
});

// Browser — first import in main.tsx / app entry
import * as Sentry from '@sentry/browser';
Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  integrations: [Sentry.browserTracingIntegration()],
  tracesSampleRate: 1.0,
});
```

### 3. Upload source maps at build time

This is the step everyone misses. Without source maps, all traces point to
minified positions forever.

```js
// vite.config.ts
import { sentryVitePlugin } from '@sentry/vite-plugin';

export default {
  build: { sourcemap: true },  // MUST emit source maps
  plugins: [
    process.env.SENTRY_AUTH_TOKEN && sentryVitePlugin({
      org: 'my-org',
      project: 'my-web',
      authToken: process.env.SENTRY_AUTH_TOKEN,
      release: { name: process.env.COMMIT_SHA },
    }),
  ].filter(Boolean),
};
```

Key rules:
- Emit source maps (`sourcemap: true`).
- Upload them to Sentry (`sentry-cli` or the framework plugin).
- **Delete them from the deploy artifact** so they're not publicly served.
- Tag every release with a git SHA so Sentry can attribute errors to a commit.

```bash
# CI step
SENTRY_AUTH_TOKEN=$TOKEN pnpm sentry-cli releases new $COMMIT_SHA
SENTRY_AUTH_TOKEN=$TOKEN pnpm sentry-cli releases set-commits $COMMIT_SHA --auto
SENTRY_AUTH_TOKEN=$TOKEN pnpm sentry-cli releases finalize $COMMIT_SHA
```

### 4. Capture meaningful context

```js
// Set user (after auth)
Sentry.setUser({ id: user.id, username: user.username });
// NEVER include passwords, tokens, emails unless you have explicit consent

// Tag for filtering
Sentry.setTag('team', 'payments');
Sentry.setTag('feature_flag', 'new-checkout');

// Add breadcrumbs for hard-to-repro bugs
Sentry.addBreadcrumb({
  category: 'ui',
  message: 'User clicked checkout button',
  level: 'info',
});

// Capture without throwing
try {
  await riskyOp();
} catch (err) {
  Sentry.captureException(err);
  // fall back to safe path
}
```

## Gotchas

- **Source maps uploaded but errors still minified**: the `release` tag on the
  Sentry event must match the release name used at upload. Mismatch by one
  character and Sentry silently can't resolve symbols. Verify in Sentry UI →
  Event → "Source Map Status".
- **Dev noise drowns prod signal**: developers' browsers and local servers
  generate hundreds of errors/day. Either (a) set `environment: 'dev'` and
  create a separate Sentry project, or (b) skip `Sentry.init` entirely when
  `NODE_ENV !== 'production'`. Don't pollute the prod project with dev errors.
- **`localhost` referrer spam**: by default Sentry captures everything. Use
  `beforeSend` to drop events where `event.request.url?.startsWith('http://localhost')`
  in prod builds — the staging environment will still get real traffic.
- **PII leakage via breadcrumbs**: the HTTP integration auto-captures request
  bodies and headers. Disable for auth / payment routes:
  ```js
  Sentry.init({
    integrations: [Sentry.httpIntegration({ tracing: { ignoreIncomingRequests: (req) => req.url.includes('/auth') } })],
  });
  ```
  Or globally: `sendDefaultPii: false` (default, but worth confirming).
- **Release ingestion race**: if the deploy goes out before `sentry-cli
  releases finalize` completes, events arrive with an unknown release and get
  bucketed under `(unknown)` permanently. Finalize **after** deploy succeeds,
  but events will retroactively resolve once the release exists.
- **CORS blocks the SDK**: the browser SDK sends events to `sentry.io` (or
  your self-hosted domain). If your CSP doesn't allow it, events fail silently
  in the console. Add `connect-src https://*.sentry.io` to your CSP.
- **Infinite loops from error handlers**: a `Sentry.captureException` call
  inside a global error handler that itself throws will recurse. Wrap capture
  in try/catch and dedupe by error message.
- **AD Blockers drop the beacon**: uBlock / Brave block `sentry.io` requests.
  In low-error environments you'll see underreporting; consider self-hosting
  or using `tunnel` route on your own origin (`Sentry.init({ tunnel: '/errors' })`
  + a worker that proxies to Sentry).
- **`replay` integration is heavy**: Session Replay captures the DOM and can
  double your bundle cost and CPU usage on slow devices. Sample at 1–10% in
  prod, not 100%.
- **Node async context loss**: `@sentry/node` uses `AsyncLocalStorage`. If you
  use `setImmediate` without context propagation, breadcrumbs lose their
  request scope. Use `Sentry.continueTrace` or stay on supported handlers.
- **Mobile (Capacitor/RN) crash-on-launch is invisible**: native crashes
  during launch never reach JS. Enable native SDK crash reporting
  (`@sentry/capacitor` does this automatically, but verify minidumps are
  uploaded — they're a separate upload path from JS events).

## What to sample where

| Environment | Errors | Traces | Profiles | Replays |
|---|---|---|---|---|
| dev | off (or 0.0) | 1.0 | 1.0 | off |
| staging | 1.0 | 1.0 | 0.5 | 0.1 |
| prod | 1.0 | 0.1–0.3 | 0.05 | 0.01–0.05 |

Errors are cheap — always capture 100% in staging/prod. Traces are expensive
(scale with traffic) — sample by traffic volume.

## See also

- `chrome-devtools-2026.md` — debugging in the browser before reaching for Sentry
- `vscode-launch-json-debugging.md` — interactive debugging locally
- `opentelemetry-local-dev.md` — performance traces (Sentry complements OTel)
