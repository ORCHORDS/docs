# Launch Handler API — PWA Launch Control on Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A Progressive Web App (PWA) served from Cloudflare Pages opens a new window every
time the user clicks a notification, a share-target link, or a file from the OS
file manager. The user ends up with ten copies of the app running in parallel, each
with its own stale state. In-flight operations (unsaved forms, pending uploads,
WebSocket connections) are duplicated. The "correct" window never comes forward
automatically, and `window.focus()` from a Service Worker is blocked by browsers
for security reasons.

## Context

The Launch Handler API lets a PWA's Web App Manifest declare a `launch_handler`
policy controlling how the browser routes new launch events to existing or new
windows. The `client_mode` field accepts:

- `"auto"` — browser decides; currently equivalent to `"navigate-new"` (default)
- `"navigate-new"` — always open a new browsing context
- `"navigate-existing"` — reuse the most recent PWA window; navigate it to the
  launch URL
- `"focus-existing"` — reuse the most recent window without navigating; deliver the
  URL via `window.launchQueue` for the page to handle itself

`window.launchQueue` is the companion JavaScript API. The browser enqueues
`LaunchParams` objects; the page drains them through a `setConsumer` callback.

Support: Chrome 110+, Edge 110+. Not in Firefox or Safari as of 2025. Feature-detect
on `'launchQueue' in window`. The manifest key is silently ignored by unsupported
browsers.

Cloudflare Pages hosts the manifest and assets. No Worker is required, although the
`_headers` file must serve the correct manifest MIME type.

---

## 1. Web App Manifest Configuration

```json
{
  "name": "Orchords Studio",
  "short_name": "Studio",
  "start_url": "/app",
  "display": "standalone",
  "launch_handler": {
    "client_mode": ["focus-existing", "auto"]
  }
}
```

`client_mode` accepts a string or an ordered array of fallback strategies. The
browser uses the first value it supports; `"auto"` as the final fallback guarantees
older browsers launch without erroring. Use `"focus-existing"` when the app manages
its own routing; use `"navigate-existing"` when navigating to the launch URL is
acceptable and the app can safely discard current state.

---

## 2. TypeScript Declarations

```typescript
interface LaunchParams {
  readonly targetURL: string | null;
  readonly files:     FileSystemFileHandle[];
}

interface LaunchQueue {
  setConsumer(consumer: (params: LaunchParams) => void): void;
}

declare global {
  interface Window {
    launchQueue?: LaunchQueue;
  }
}

function supportsLaunchHandler(): boolean {
  return typeof window !== 'undefined' && 'launchQueue' in window;
}
```

---

## 3. Draining the Launch Queue

```typescript
type LaunchConsumer = (params: LaunchParams) => void | Promise<void>;

function initLaunchHandler(onLaunch: LaunchConsumer): void {
  if (!supportsLaunchHandler()) return;

  window.launchQueue!.setConsumer(async (params) => {
    try {
      await onLaunch(params);
    } catch (err) {
      console.error('Launch handler error:', err);
    }
  });
}

// SPA: intercept the launch URL and push it to the history stack
initLaunchHandler(async ({ targetURL }) => {
  if (!targetURL) return;          // icon launch — no URL to handle

  const url      = new URL(targetURL);
  const relative = url.pathname + url.search + url.hash;

  // Update the address bar without reloading
  history.pushState({}, '', relative);
  window.dispatchEvent(new PopStateEvent('popstate', { state: null }));
  window.focus();
});
```

`setConsumer` may be called only once per page load. A second call silently replaces
the previous consumer. Register the consumer as early as possible in the page
lifecycle — the browser may enqueue params before the page finishes loading.

---

## 4. File Handling via launchQueue

The `files` array holds `FileSystemFileHandle` objects when the OS opened a file
using the app's registered `file_handlers`. Access is pre-granted; no permission
prompt is shown.

```typescript
type FileProcessor = (file: File) => Promise<void>;

function initFileHandlingLaunch(processFile: FileProcessor): void {
  initLaunchHandler(async ({ files }) => {
    for (const handle of files) {
      try {
        const file = await handle.getFile();
        await processFile(file);
      } catch (err) {
        console.error('Failed to process launch file:', (handle as FileSystemHandle).name, err);
      }
    }
  });
}

// This pairs with the manifest file_handlers field:
// "file_handlers": [{
//   "action": "/app",
//   "accept": { "image/*": [".png", ".jpg", ".webp"] }
// }]
```

---

## 5. React Router Integration

```typescript
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

function useLaunchHandler(): void {
  const navigate = useNavigate();

  useEffect(() => {
    if (!supportsLaunchHandler()) return;

    window.launchQueue!.setConsumer(({ targetURL }) => {
      if (!targetURL) return;

      const url      = new URL(targetURL);
      const relative = url.pathname + url.search + url.hash;
      navigate(relative, { replace: false });
    });
  }, [navigate]);  // navigate reference is stable in React Router v6+
}

// Register once at the root level:
function App() {
  useLaunchHandler();
  return <RouterOutlet />;
}
```

In React StrictMode the effect runs twice in development; `setConsumer` is
effectively idempotent (new consumer replaces old), so this is safe in practice.

---

## 6. Manifest Hosting on Cloudflare Pages

Cloudflare Pages may not infer `application/manifest+json` from the `.webmanifest`
extension alone. Set the MIME type explicitly in the `_headers` file.

```
# public/_headers
/manifest.webmanifest
  Content-Type: application/manifest+json
  Cache-Control: public, max-age=3600

/manifest.json
  Content-Type: application/manifest+json
  Cache-Control: public, max-age=3600
```

An incorrect Content-Type causes Chrome to ignore the manifest silently — no console
error, no installation prompt. Keep the manifest cache short (`max-age=3600` or
lower) during active development so `launch_handler` changes take effect quickly
after deploy.

---

## 7. Verifying Focus Behaviour in the Installed PWA

```typescript
// Smoke test: confirm consumer registers and fires
if (supportsLaunchHandler()) {
  window.launchQueue!.setConsumer((params) => {
    console.log('Launch params:', {
      targetURL: params.targetURL,
      fileCount: params.files.length,
    });
  });
  console.log('Launch handler registered');
} else {
  console.log('Launch Handler API not supported');
}
```

Full test requires an installed PWA. Install via Chrome → three-dot menu → Install,
then trigger a launch from outside the app (OS file open, notification click, or
`google-chrome --app=<url>`).

---

## Anti-patterns

- Calling `setConsumer` inside a render function. Consumer registration is a side
  effect; call it from `useEffect` or a module-level init function, not during
  render where it runs on every re-render.
- Using `"navigate-existing"` when the app has unsaved state. The browser navigates
  away from the current URL; any unsaved editor content, form input, or in-memory
  state is silently destroyed.
- Expecting `targetURL` to always be non-null. When the user launches from the
  homescreen icon (not a deep link or file), `targetURL` is `null`. Guard every
  access.
- Registering `file_handlers` in the manifest without pairing a launchQueue
  consumer to process `params.files`. Opened files are silently dropped.

## Gotchas

- `focus-existing` only focuses within the same origin. A launch URL on a different
  subdomain (e.g., `api.example.com`) will not focus a window at `app.example.com`.
- On macOS, `window.focus()` may not bring the browser to the foreground if the
  user has not recently interacted with the window. The OS restricts app-initiated
  focus steals and a banner notification is shown instead.
- The `launchQueue` consumer is not called during a normal page navigation or
  refresh — only when the OS routes a launch event to the PWA (file open, protocol
  handler, notification click, etc.).
- When Cloudflare Pages deploys a new version, the browser may continue using a
  cached `manifest.webmanifest` for up to `max-age` seconds. Aggressive caching
  of the manifest can delay `launch_handler` changes reaching installed PWAs.
- The `"focus-existing"` mode requires the PWA to be installed. If the user opens
  the page in a regular browser tab (not the standalone PWA window), the behaviour
  falls back to `"auto"`.

## Verification

```bash
# 1. Install the PWA in Chrome (desktop):
#    Three-dot menu → Save and share → Install page as app

# 2. Trigger a re-launch from the terminal:
google-chrome --app=https://your-pages-site.pages.dev/app/document/42

# 3. Expected with focus-existing:
#    Existing PWA window comes forward; no new window opens
#    Console logs "Launch params: { targetURL: '.../document/42', fileCount: 0 }"
```

## Related

- `pwa-manifest-config.md`
- `pwa-service-worker-cloudflare-pages.md`
- `browser-file-system-access.md`
- `web-share-target-ingress-validation.md`
- `origin-private-file-system-opfs-cloudflare-pages.md`

## Sources

- WICG Web App Launch Handler — https://wicg.github.io/web-app-launch/
- MDN LaunchQueue — https://developer.mozilla.org/en-US/docs/Web/API/LaunchQueue
- Chrome Developers: Launch Handler — https://developer.chrome.com/docs/capabilities/web-apis/launch-handler
- Chrome Platform Status — https://chromestatus.com/feature/5722383233056768
