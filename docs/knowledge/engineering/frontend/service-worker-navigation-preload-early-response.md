# Service Worker Navigation Preload Early Response

## Scope

Using the Navigation Preload mechanism — `registration.navigationPreload.enable()` on the service worker and the `Service-Worker-Navigation-Preload` request header on the server — to start the network request for a navigation while the service worker is still starting up. Covers the latency problem it solves, the request/response contract, streaming the preloaded response, header validation for security, and lifecycle pitfalls during rollout. Excludes general service worker caching strategy and excludes the fetch-event cache-first patterns covered elsewhere in this leaf.

## Workflow or implementation guidance

Without navigation preload, a cold service worker adds its own startup to the critical path of every navigation it handles: browser starts the worker, the worker boots, the `fetch` handler runs, and only then does the handler's `fetch()` call hit the network. On mid-tier mobile devices that startup is commonly tens to hundreds of milliseconds, paid on every navigation after a worker was stopped.

Preload removes the serialization by starting the navigation request in parallel with worker startup. The server sees a normal navigation request plus one extra header, and its response is waiting for the handler by the time the handler runs.

Enablement is per-registration and belongs in the activate handler, after old workers are gone.

```js
self.addEventListener('install', (e) => e.waitUntil(self.skipWaiting()));

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    if (self.registration.navigationPreload) {
      await self.registration.navigationPreload.enable();
    }
    await self.clients.claim();
  })());
});
```

The fetch handler consumes the in-flight response through the event's preload response promise rather than issuing a second request.

```js
self.addEventListener('fetch', (e) => {
  if (e.request.mode !== 'navigate') return;

  e.respondWith((async () => {
    try {
      const preloaded = e.preloadResponse;
      if (preloaded) {
        const res = await preloaded;
        if (res && res.ok) return res;
      }
      return await fetch(e.request);
    } catch {
      return caches.match('/offline')
        ?? new Response('offline', { status: 503 });
    }
  })());
});
```

`e.preloadResponse` resolves with the `Response` or `null`. It is `null` when preload is not enabled for this registration, when the navigation is not eligible (for example a prerendered or bfcached navigation), or when the worker was already running and the browser skipped the optimization. Always check for `null` and fall back to a normal `fetch`; treating a null preload as an error breaks navigations in the states above.

Server side, the request arrives with `Service-Worker-Navigation-Preload: true` (the default header value; the spec permits the value to be set to a site-specific string via `setState`). The server can use it to return a lighter payload for shell navigations — for example skipping the full HTML wrapper's data blocks that the client will fetch anyway. Because the header is settable by the site's own worker, treat it as a hint, not an authorization signal; anything sensitive still requires real authentication on the request.

```js
// streaming variant: pass the body through without buffering
const res = await e.preloadResponse;
if (res && res.ok) return res; // body streams to the page as it arrives
```

Returning the response object directly (not `res.text()` then re-wrapping) preserves streaming: the document begins parsing while the server is still sending, which is where the largest wins on slow backends.

Rollout order matters. A worker that handles `e.preloadResponse` before the server understands the header is safe (the header is ignored server-side). The reverse order — server returns different payloads based on the header while old workers never send it — is also safe, because old workers send no header and get the default payload. The unsafe combination is disabling preload on the worker while the server still depends on the header for correctness; the header simply stops arriving, and the server must treat absence as the default path.

## Controls

- `navigationPreload.enable()` in `activate`, guarded by feature detection on `self.registration.navigationPreload`.
- `e.preloadResponse` awaited inside `respondWith`, with an explicit null check and `fetch(e.request)` fallback.
- Error path with an offline fallback from cache, since preload does not change network failure behavior.
- Server treats `Service-Worker-Navigation-Preload` as a payload hint only; authentication and authorization decisions never depend on it.
- `navigationPreload.setState(value)` if the backend needs to distinguish worker versions or request shapes; the value arrives in the same header.

## Validation evidence

- Measure navigation timing before and after: compare `fetchStart` to `responseStart` in `PerformanceNavigationTiming` for cold-worker navigations; the gap should shrink by roughly the worker startup time.
- Force a cold worker between measurements (unregister, or wait out the idle termination timer) so the comparison captures startup, not the warm path.
- Verify the header server-side from access logs or an echo endpoint during rollout, confirming which navigations actually carry it.
- Assert the offline fallback still works with preload enabled by throttling the network to offline in an automated browser test that navigates a controlled page.

## Failure modes and correction

- `e.preloadResponse` used without a null check: navigations without preload (feature disabled, ineligible navigation, or the promise resolving null) fall through to no response. Always branch on the resolved value.
- Calling `fetch(e.request)` in addition to consuming `preloadResponse`: two network requests for one navigation, doubling backend load. Consume one or the other.
- Enabling preload in `install` instead of `activate`: the running worker's registration state and the requests it sees can disagree during the update window; enable on activate so it takes effect for the worker that owns the scope.
- Server varies the response on the header but the CDN strips unknown request headers: the hint never arrives and payload selection silently reverts; add the header to the CDN allow-list and cache-key policy as a non-varying pass-through.
- Returning a rewritten body (`await res.text()` then a new `Response`) defeats streaming and re-adds latency; return the original response or transform with streams.
- Wagering correctness on the header's presence (serving unauthenticated data because "only my worker sends it"): the header is client-settable; keep real auth checks.

## Limitations

- Applies to navigation requests only; subresource requests do not get a preload path through this mechanism.
- The optimization only pays on cold or restarting workers; a long-lived warm worker sees `preloadResponse` resolve null and takes the normal path.
- Prerendered documents and pages restored from back/forward cache are not eligible, so measured averages depend heavily on the navigation mix.
- The preloaded response is produced by the browser's navigation request, so request customization (different headers, different URL) is limited to `setState`'s header value; anything more requires abandoning preload for that navigation.
- Cross-browser support excludes some older evergreen versions; feature-detect `navigationPreload` on the registration and keep the plain fetch path.

## Canonical sources

- W3C, Service Worker spec, navigation preload: https://w3c.github.io/ServiceWorker/#navigation-preload
- MDN, `ServiceWorkerRegistration.navigationPreload`: https://developer.mozilla.org/en-US/docs/Web/API/ServiceWorkerRegistration/navigationPreload
- MDN, `PerformanceNavigationTiming`: https://developer.mozilla.org/en-US/docs/Web/API/PerformanceNavigationTiming
- W3C, Navigation Timing Level 2: https://w3c.github.io/navigation-timing/
