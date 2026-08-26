# pwa-manifest-config

**Issue:** Missing or misconfigured web app manifest prevents the install prompt and PWA features
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The "Add to Home Screen" prompt never appears; the app is not installable on Android.

## Pattern / Solution
```json
// public/manifest.json
{
  "name": "My App",
  "short_name": "App",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#3b82f6",
  "icons": [
    { "src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png" },
    { "src": "/icons/icon-512-maskable.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ],
  "screenshots": [
    { "src": "/screenshots/desktop.png", "sizes": "1280x800", "form_factor": "wide" }
  ]
}
```

```html
<link rel="manifest" >
<meta name="theme-color" content="#3b82f6">
<meta name="apple-mobile-web-app-capable" content="yes">
```

## Gotchas
- Both maskable and any-purpose icons are required for Android
- display: standalone hides browser UI; minimal-ui shows a small bar
- HTTPS is required for PWA installability (except localhost)
- iOS Safari ignores the manifest; use Apple-specific meta tags for full support

## Related
- `browser-service-worker-cache.md`
- `offline-fallback-pages.md`
