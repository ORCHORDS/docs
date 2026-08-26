# pwa-background-sync

**Issue:** Deferring failed network requests to sync when connectivity returns in a PWA
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users submit forms or actions while offline. Without background sync, these are lost on page close. The Background Sync API lets the service worker retry the request when the network is available, even if the tab is closed.

## Pattern / Solution
**Register a sync tag:**
```ts
// In main app code
async function sendMessage(message: Message) {
  try {
    await api.postMessage(message);
  } catch {
    // Store in IndexedDB for later
    await db.pendingMessages.add(message);
    const registration = await navigator.serviceWorker.ready;
    await registration.sync.register('sync-messages');
  }
}
```

**Handle sync in service worker:**
```js
// sw.js
self.addEventListener('sync', event => {
  if (event.tag === 'sync-messages') {
    event.waitUntil(syncPendingMessages());
  }
});

async function syncPendingMessages() {
  const db = await openDB('app-db', 1);
  const messages = await db.getAll('pendingMessages');

  for (const message of messages) {
    try {
      await fetch('/api/messages', {
        method: 'POST',
        body: JSON.stringify(message),
        headers: { 'Content-Type': 'application/json' },
      });
      await db.delete('pendingMessages', message.id);
    } catch {
      throw new Error('Sync failed'); // retry on next connectivity
    }
  }
}
```

**Periodic Background Sync (Chrome, requires installation):**
```ts
const registration = await navigator.serviceWorker.ready;
const status = await navigator.permissions.query({ name: 'periodic-background-sync' as any });
if (status.state === 'granted') {
  await registration.periodicSync.register('content-sync', {
    minInterval: 24 * 60 * 60 * 1000, // 24 hours
  });
}
```

```js
// sw.js
self.addEventListener('periodicsync', event => {
  if (event.tag === 'content-sync') {
    event.waitUntil(updateContent());
  }
});
```

## Gotchas
- Background Sync is Chrome/Edge only as of 2026; Safari does not support it
- The sync event fires once the device has network connectivity — not at a specific time
- Failed sync (thrown error in `event.waitUntil`) causes the browser to retry with exponential backoff
- Periodic Background Sync requires the PWA to be installed and the user to grant permission
- IndexedDB is the only reliable storage in a service worker; `localStorage` is not accessible

## Related
- `pwa-service-worker-patterns.md`
- `pwa-offline-caching-strategies.md`
- `react-native-offline-first.md`
