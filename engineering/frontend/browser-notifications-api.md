# browser-notifications-api

**Issue:** Requesting notification permission on page load triggers high denial rates
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Push notification opt-in rates are below 5% because the permission prompt appears immediately on first visit.

## Pattern / Solution
```ts
// Request at the right moment (after user signals interest)
async function enableNotifications() {
  if (Notification.permission === 'denied') {
    showSettingsInstructions();
    return;
  }
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return;

  // Subscribe to push (requires service worker)
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
  });
  await saveSubscription(subscription);
}

// Show a notification from service worker
self.registration.showNotification('New message', {
  body: 'You have 3 unread messages',
  icon: '/icon.png',
  badge: '/badge.png',
  data: { url: '/messages' },
});
```

## Gotchas
- Push notifications require a service worker; they work even when the app is closed
- VAPID keys are required for Web Push; generate with web-push npm package
- iOS Safari added Web Push support in iOS 16.4 for installed PWAs only

## Related
- `browser-permissions-api.md`
- `browser-service-worker-cache.md`
