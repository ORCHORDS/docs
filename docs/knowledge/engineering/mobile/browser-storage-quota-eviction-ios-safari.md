# Mobile Browser Storage Limits and Eviction

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

iOS Safari users on example project report being suddenly "logged out",
wallet disconnected, or feed empty after a period of inactivity
— symptoms desktop users never experience. Support tickets
describe the issue as intermittent and hard to reproduce. The
root cause is Safari's Intelligent Tracking Prevention (ITP)
silently evicting all script-writable storage — IndexedDB,
Cache API, localStorage, Service Worker registrations — after 7
days of inactivity on the origin. Age-gate session tokens
disappear. Solana wallet adapter state is cleared. Cached feed
content vanishes. No error is thrown; the storage simply ceases
to exist at the next app visit.

## Context

All browsers enforce per-origin storage quotas and have eviction
policies. On desktop, quotas are generous and proactive eviction
is rare. On mobile — especially iOS Safari — quotas were
historically tighter and eviction is silent and automatic. The
gap is widest on iOS: every third-party browser on iOS (Chrome,
Firefox, Brave) uses the WebKit engine under the hood and
inherits Safari's storage restrictions and ITP behaviour. There
is no escape via browser choice on iOS. Storage APIs affected:
IndexedDB (structured data, wallet state), Cache API (Service
Worker offline cache), localStorage (session flags), and OPFS
(Origin Private File System, large binary assets). All live in
the same storage bucket and are evicted together.

## Platform quota comparison

```
Platform / mode          Per-origin quota
──────────────────────────────────────────────────────────────
Chrome desktop           60% of total disk (both modes)
Chrome Android           60% of total disk (both modes)
Firefox desktop          10% disk or 10 GiB (best-effort)
                         50% disk, max 8 TiB (persistent)
Firefox Android          10% disk or 10 GiB (best-effort)
Safari 17+ / iOS 17+
  Browser / Home Screen  ~60% of total disk
  Embedded WKWebView     ~15% of total disk
  Cross-origin iframes   10% of parent origin's quota
  Overall all-origins    80% of disk (browser), 20% (WKWebView)
Safari < 17 / iOS < 17   1 GiB initial; user prompted to expand

Private Browsing: lower quotas everywhere, deleted on exit.
Chrome Incognito: ~5% of disk.

All iOS browsers (Chrome, Firefox, Brave) share WebKit quotas
because they must use the WebKit engine on iOS. Safari 17+
lifted the 1 GiB cap — but ITP eviction remains unchanged.
```

## Safari 7-day ITP eviction rule

```
ITP (Intelligent Tracking Prevention) proactively deletes ALL
script-writable storage for an origin when there has been no
user interaction (tap, click) on that origin for 7 or more days
of Safari use.

Storage deleted (atomically — the entire origin at once):
  - IndexedDB databases
  - Cache API entries (including all Service Worker caches)
  - localStorage and sessionStorage
  - Service Worker registrations
  - OPFS entries

NOT deleted:
  - Server-set cookies (Set-Cookie / HttpOnly)
  - Data in confirmed persistent storage mode

Scope: whole-origin wipe. No partial deletion; all storage
types disappear together in a single eviction event.

Clock: "7 days of Safari use" — not 7 calendar days. The timer
advances only when the user actively opens Safari. A user who
rarely uses Safari accumulates fewer Safari-use days.

Key exception: origins installed as Home Screen Web Apps are
treated with browser-level heuristics and are NOT subjected to
the same 7-day proactive wipe. Installing as a Home Screen app
is the most reliable path to durable storage on iOS short of
the user explicitly granting navigator.storage.persist().
```

## Quota API — checking available space

```javascript
// Call on app init. On iOS, actual quota is often far below
// what desktop tests suggest. Log results to analytics.

async function checkStorageQuota() {
  if (!navigator.storage?.estimate) return null;

  const { usage, quota } = await navigator.storage.estimate();
  const usedMB  = (usage  / 1024 / 1024).toFixed(1);
  const quotaMB = (quota  / 1024 / 1024).toFixed(1);
  const pct     = ((usage / quota) * 100).toFixed(1);

  console.log(`Storage: ${usedMB}MB / ${quotaMB}MB (${pct}%)`);

  // estimate() returns approximations — browsers pad values
  // for fingerprinting resistance. Do not rely on exact bytes.
  return { usedMB, quotaMB, pct };
}
```

## navigator.storage.persist() — requesting durable storage

```javascript
// Persistent mode opts out of automatic LRU eviction.
// On iOS: almost never granted for a regular browser tab.
// More likely granted if the origin is a Home Screen Web App.
// No UI prompt on Safari — resolves true or false silently.

async function requestPersistentStorage() {
  if (!navigator.storage?.persist) return false;

  if (await navigator.storage.persisted()) return true; // done

  const granted = await navigator.storage.persist();

  if (!granted) {
    // Surface a prompt encouraging Home Screen install.
    // That is the practical durability path on iOS.
    showInstallPrompt();
  }
  return granted;
}

// Safari heuristics (undocumented, inferred from WebKit source):
//   Home Screen Web App               → likely true
//   High-frequency daily visits       → possible
//   Infrequent visits in browser tab  → almost always false
```

## OPFS for large structured data

```
Origin Private File System (OPFS) — sandboxed file-system
inside the origin's storage bucket.

Support matrix:
  iOS / Safari   Available since iOS 15.2 / Safari 15.2 (Dec 2021)
  Chrome         Full support (desktop and Android)
  Firefox        Full support (desktop and Android)
  Private mode   NOT available on Safari in Private Browsing

Eviction: OPFS lives in the same storage bucket as IndexedDB.
ITP evicts OPFS together with all other script storage. OPFS
does NOT escape the 7-day rule unless the origin is in
confirmed persistent mode.

When to prefer OPFS over IndexedDB:
  - Large binary blobs (audio, video, images > 10 MB)
  - SQLite running in WASM (e.g., local Solana state DB)
  - Synchronous file I/O needed inside a Web Worker

Still pair with navigator.storage.persist() — OPFS alone
provides no eviction protection beyond IndexedDB.
```

## Eviction detection and graceful recovery

```javascript
// Version stamp written to localStorage on every app init.
// A missing or mismatched stamp on return visit = eviction.
// Treat it as a first-run, not as a corrupt/broken state.

const STAMP_KEY = 'example project_storage_stamp';
const STAMP_VAL = '2024-10'; // rotate when schema changes

async function detectAndRecoverEviction() {
  try {
    const stored = localStorage.getItem(STAMP_KEY);
    if (stored === STAMP_VAL) return; // storage intact

    const wasEvicted = stored !== null; // null = first run
    if (wasEvicted) {
      analytics.track('storage_evicted', {
        ua: navigator.userAgent,
        platform: navigator.platform,
      });
      // Clear stale adapter state, trigger re-auth
      await clearWalletAdapterState();
      await redirectToReauth({ reason: 'storage_evicted' });
    }
    localStorage.setItem(STAMP_KEY, STAMP_VAL);
  } catch (e) {
    // localStorage may throw in Private Browsing when
    // the quota is exhausted. Treat as ephemeral session.
    console.warn('Storage unavailable — running ephemeral:', e);
  }
}

// Distinguish QuotaExceededError from network / schema errors.
async function safeWrite(store, key, value) {
  try {
    await store.put(value, key);
  } catch (err) {
    if (err.name === 'QuotaExceededError') {
      // Storage full — prune then retry once.
      await pruneOldEntries(store);
      await store.put(value, key); // may still throw
    } else {
      throw err; // not a quota issue — let caller handle
    }
  }
}
```

## Anti-patterns

- **Storing auth tokens only in localStorage** — ITP evicts
  localStorage with everything else. Critical auth state must
  be backed by server-set HttpOnly cookies that survive eviction.
- **Assuming iOS Chrome behaves like desktop Chrome** — all iOS
  browsers use WebKit. ITP applies to Chrome, Firefox, and Brave
  on iOS just as it does to Safari.
- **Treating QuotaExceededError as a network error** — storage
  writes throw synchronously (or reject a Promise) with
  `QuotaExceededError`. Network fetch errors are async and
  caught via different code paths. Conflating them produces
  misleading error logs and wrong recovery logic.
- **Calling navigator.storage.persist() without a UX plan** —
  on iOS regular tabs it returns false silently. If durability
  matters, use the result to surface a Home Screen install
  prompt — that is the actionable next step for the user.
- **Relying on OPFS as an eviction escape hatch** — OPFS is in
  the same bucket as IndexedDB. ITP evicts both together.

## Gotchas

- **"7 days of Safari use" not 7 calendar days** — the ITP timer
  only advances when the user actively opens Safari. An
  infrequent Safari user may go weeks without triggering it.
- **All-or-nothing eviction** — Safari evicts the entire origin
  atomically. Partial data loss does not happen; the whole bucket
  is wiped in one event, which can look like a catastrophic app
  failure rather than a storage policy.
- **navigator.storage.estimate() is approximate** — browsers add
  noise to usage and quota values for fingerprinting resistance.
  Never gate critical logic on exact byte equality.
- **Cross-origin iframes inherit reduced quota** — an embedded
  frame gets ~10% of the parent origin's quota. Wallet adapter
  iframes or embedded age-gate flows may hit limits far sooner.
- **Private Browsing is always ephemeral on iOS** — OPFS is
  unavailable, quotas are lower, and all storage is deleted when
  the private tab is closed. Detect and surface a warning.
- **Safari 17+ lifted the 1 GiB cap but not ITP** — the larger
  disk-based quota in iOS 17+ is welcome, but the 7-day
  eviction rule is unaffected. Do not confuse the two changes.

## Verification

- `navigator.storage.estimate()` called on init; `usage`,
  `quota`, and percentage logged to analytics by platform/UA.
- `navigator.storage.persist()` result (true/false) tracked
  per session; false triggers Home Screen install prompt.
- Storage version stamp checked on every app open; mismatch
  triggers eviction-aware re-auth rather than broken state.
- `QuotaExceededError` caught separately from network errors
  in all IndexedDB and Cache API write paths.
- Solana wallet adapter connection state backed by server-side
  session cookie so reconnect survives a storage wipe.
- Age-gate session token stored in HttpOnly cookie (not
  localStorage) so it persists through ITP eviction events.
- Home Screen install prompt surfaced post-auth on iOS to
  maximize `persist()` grant rate and eviction immunity.

## Related

- `documentation/docs/policies/mobile/pwa-offline-caching-strategies.md`
- `documentation/docs/policies/mobile/pwa-service-worker-patterns.md`
- `documentation/docs/policies/mobile/pwa-stale-assets-cloudflare-pages-ios-safari.md`

## Source URLs (verified 2026-08-17)

- Updates to Storage Policy (WebKit) — https://webkit.org/blog/14403/updates-to-storage-policy/
- Storage quotas and eviction criteria (MDN) — https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- The File System API with Origin Private File System (WebKit) — https://webkit.org/blog/12257/the-file-system-access-api-with-origin-private-file-system/
- Safari iOS PWA Data Persistence Beyond 7 Days (Apple Developer Forums) — https://developer.apple.com/forums/thread/710157
- Is Safari still evicting IndexedDB after 7 days? (Hacker News) — https://news.ycombinator.com/item?id=34266444
