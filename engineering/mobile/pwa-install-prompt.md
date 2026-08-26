# pwa-install-prompt

**Issue:** Triggering and customizing the PWA install prompt (Add to Home Screen)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Browsers show an "Add to Home Screen" prompt for qualifying PWAs. The default timing is often wrong (too early). Capturing the `beforeinstallprompt` event lets you show the prompt at the right moment.

## Pattern / Solution
**Capture and defer the prompt:**
```ts
let deferredPrompt: BeforeInstallPromptEvent | null = null;

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault(); // stop automatic prompt
  deferredPrompt = e as BeforeInstallPromptEvent;
  showInstallBanner(); // show your custom UI
});
```

**Trigger install on user action:**
```ts
async function handleInstallClick() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log('User response:', outcome); // 'accepted' | 'dismissed'
  deferredPrompt = null;
  hideInstallBanner();
}
```

**Detect if already installed:**
```ts
const isInstalled = window.matchMedia('(display-mode: standalone)').matches
  || (navigator as any).standalone === true; // iOS Safari
```

**Track install via analytics:**
```ts
window.addEventListener('appinstalled', () => {
  analytics.track('pwa_installed');
  deferredPrompt = null;
});
```

**Web App Manifest (required):**
```json
{
  "name": "My App",
  "short_name": "MyApp",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#0066cc",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
```

## Gotchas
- `beforeinstallprompt` is Chrome/Edge only; Safari uses its own flow (no API, user must use Share → Add to Home Screen)
- PWA installability criteria: HTTPS, valid manifest with icons, at least one service worker with a fetch handler
- `deferredPrompt` is single-use; after calling `.prompt()`, it cannot be reused
- iOS standalone mode doesn't support Push API unless the PWA is opened via Safari first
- Maskable icons are required for Android adaptive icon support; without them, icons get letterboxed

## Related
- `pwa-service-worker-patterns.md`
- `pwa-web-push-notifications.md`
- `pwa-offline-caching-strategies.md`
