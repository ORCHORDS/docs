# pwa-web-push-notifications

**Issue:** Implementing push notifications in a Progressive Web App
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Web Push allows PWAs to receive notifications even when the browser is closed (on supported platforms). It requires VAPID keys, a Push API subscription, and a service worker to display the notification.

## Pattern / Solution
**Generate VAPID keys (once, store on server):**
```bash
npx web-push generate-vapid-keys
# VAPID_PUBLIC_KEY=BEl62...
# VAPID_PRIVATE_KEY=kF3...
```

**Subscribe in the browser:**
```ts
async function subscribeToPush(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.ready;
  const existing = await registration.pushManager.getSubscription();
  if (existing) return existing;

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return null;

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true, // required by Chrome
    applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
  });

  await sendToBackend(subscription); // store { endpoint, keys }
  return subscription;
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - base64.length % 4) % 4);
  const base64Url = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/');
  return Uint8Array.from(atob(base64Url), c => c.charCodeAt(0));
}
```

**Send push from server (Node.js):**
```ts
import webpush from 'web-push';
webpush.setVapidDetails('mailto:admin@example.com', VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);

await webpush.sendNotification(subscription, JSON.stringify({
  title: 'New message',
  body: 'You have a new message from Alice',
  icon: '/icons/icon-192.png',
  data: { url: '/messages/42' },
}));
```

**Handle in service worker:**
```js
self.addEventListener('push', event => {
  const data = event.data?.json() ?? { title: 'Notification', body: '' };
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: data.icon ?? '/icons/icon-192.png',
      data: data.data,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data.url ?? '/'));
});
```

## Gotchas
- iOS added Web Push support in Safari 16.4 / iOS 16.4 (2023); it requires the PWA to be installed to the home screen
- Subscriptions expire or are invalidated by the browser — always handle 410 Gone responses from the push service by deleting the subscription
- `userVisibleOnly: true` is currently mandatory; silent push (for data sync) is not yet standardized
- The push payload is limited to ~4 KB
- Chrome requires HTTPS; Firefox allows localhost

## Related
- `pwa-service-worker-patterns.md`
- `pwa-install-prompt.md`
- `react-native-push-notifications.md`
