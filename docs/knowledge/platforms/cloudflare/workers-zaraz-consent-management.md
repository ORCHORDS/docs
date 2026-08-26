# Implementing Consent Management with Cloudflare Zaraz

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your site uses Cloudflare Zaraz to load third-party tools (Google Analytics, Meta Pixel, Intercom). Under GDPR and ePrivacy rules, you must obtain explicit user consent before loading tracking tools. Naively blocking all scripts until consent causes flicker and broken analytics. You need a solution that: blocks tools server-side until consent is given, persists consent choices, and forwards server-side events only for consented tools — all without a third-party CMP vendor.

## Context

Zaraz is Cloudflare's server-side tag manager. Unlike traditional client-side tag managers, Zaraz intercepts `zaraz.track()` calls in the browser, sends them to the Zaraz Worker at Cloudflare's edge, and the Worker forwards events to third-party destinations. This architecture means:

- Third-party scripts are never loaded in the browser (Zaraz acts as a proxy).
- Consent can be enforced server-side in the Zaraz Worker, preventing data from leaving Cloudflare until consent is granted.
- The Zaraz Consent API (`zaraz.consent`) provides a JavaScript interface for reading and writing per-purpose consent state in the browser.

Zaraz organises tools into consent purposes (e.g. `analytics`, `marketing`, `functional`). Each purpose can be toggled independently.

## Solution

```typescript
// zaraz-consent-worker/src/index.ts
// Custom Zaraz Worker with consent enforcement and KV persistence.

export interface Env {
  CONSENT_KV: KVNamespace;
  ZARAZ_TOKEN: string;
}

const PURPOSES = {
  analytics: 'analytics',
  marketing: 'marketing',
  functional: 'functional',
} as const;

type Purpose = keyof typeof PURPOSES;

interface ConsentRecord {
  purposes: Record<Purpose, boolean>;
  timestamp: number;
  version: number;
}

function consentKey(uid: string): string {
  return `consent:${uid}`;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/zaraz/consent' && request.method === 'GET') {
      return handleGetConsent(request, env);
    }
    if (url.pathname === '/zaraz/consent' && request.method === 'POST') {
      return handleSetConsent(request, env);
    }

    return fetch(request);
  },
};

async function handleGetConsent(
  request: Request,
  env: Env,
): Promise<Response> {
  const uid = getUid(request);

  if (!uid) {
    return Response.json(defaultConsent(), {
      headers: { 'Cache-Control': 'no-store' },
    });
  }

  const record = await env.CONSENT_KV.get<ConsentRecord>(
    consentKey(uid),
    'json',
  );

  return Response.json(record ?? defaultConsent(), {
    headers: { 'Cache-Control': 'no-store' },
  });
}

async function handleSetConsent(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{ purposes: Record<string, boolean> }>();

  const validated: Record<Purpose, boolean> = {
    analytics: false,
    marketing: false,
    functional: false,
  };

  for (const [key, value] of Object.entries(body.purposes)) {
    if (key in PURPOSES) {
      validated[key as Purpose] = Boolean(value);
    }
  }

  const record: ConsentRecord = {
    purposes: validated,
    timestamp: Date.now(),
    version: 1,
  };

  let uid = getUid(request);
  const isNew = !uid;
  uid = uid ?? crypto.randomUUID();

  // Persist consent in KV with a 13-month TTL (GDPR consent validity period)
  await env.CONSENT_KV.put(consentKey(uid), JSON.stringify(record), {
    expirationTtl: 60 * 60 * 24 * 395,
  });

  const headers = new Headers({
    'Content-Type': 'application/json',
    'Cache-Control': 'no-store',
  });

  if (isNew) {
    headers.set(
      'Set-Cookie',
      [
        `zaraz_uid=${uid}`,
        'Path=/',
        'Max-Age=34128000',
        'SameSite=Lax',
        'Secure',
        'HttpOnly',
      ].join('; '),
    );
  }

  return new Response(JSON.stringify({ ok: true, uid }), {
    status: 200,
    headers,
  });
}

function getUid(request: Request): string | null {
  const cookie = request.headers.get('Cookie') ?? '';
  const match = cookie.match(/zaraz_uid=([^;]+)/);
  return match?.[1] ?? null;
}

function defaultConsent(): ConsentRecord {
  return {
    purposes: { analytics: false, marketing: false, functional: false },
    timestamp: 0,
    version: 1,
  };
}
```

**Client-side consent modal integration:**

```typescript
// src/consent-modal.ts

declare global {
  interface Window {
    zaraz: {
      consent: {
        modal: boolean;
        setAll: (value: boolean) => void;
        set: (purposeId: string, value: boolean) => void;
        get: (purposeId: string) => boolean | undefined;
        getAll: () => Record<string, boolean>;
        sendQueuedEvents: () => void;
      };
      track: (event: string, properties?: Record<string, unknown>) => void;
    };
  }
}

interface ConsentChoices {
  analytics: boolean;
  marketing: boolean;
  functional: boolean;
}

export async function initConsent(): Promise<void> {
  const res = await fetch('/zaraz/consent');
  const record = await res.json<{ purposes: ConsentChoices; timestamp: number }>();

  if (record.timestamp > 0) {
    applyConsentToZaraz(record.purposes);
    return;
  }

  showConsentModal();
}

function applyConsentToZaraz(purposes: ConsentChoices): void {
  for (const [purposeId, granted] of Object.entries(purposes)) {
    window.zaraz.consent.set(purposeId, granted);
  }
  window.zaraz.consent.sendQueuedEvents();
}

function showConsentModal(): void {
  const modal = document.createElement('div');
  modal.id = 'consent-modal';
  modal.innerHTML = `
    <div class="consent-overlay">
      <div class="consent-box">
        <h2>Your Privacy Choices</h2>
        <p>We use tools to improve your experience and measure site performance.
           You can choose which categories to allow.</p>
        <label>
          <input type="checkbox" name="analytics" checked />
          Analytics (site usage statistics)
        </label>
        <label>
          <input type="checkbox" name="marketing" />
          Marketing (personalised ads)
        </label>
        <label>
          <input type="checkbox" name="functional" checked />
          Functional (chat, support widgets)
        </label>
        <button id="consent-accept-all">Accept All</button>
        <button id="consent-save">Save Choices</button>
        <button id="consent-reject-all">Reject All</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  document.getElementById('consent-accept-all')!.addEventListener('click', () =>
    saveAndClose({ analytics: true, marketing: true, functional: true }),
  );
  document.getElementById('consent-reject-all')!.addEventListener('click', () =>
    saveAndClose({ analytics: false, marketing: false, functional: false }),
  );
  document.getElementById('consent-save')!.addEventListener('click', () => {
    const choices: ConsentChoices = {
      analytics: (modal.querySelector('[name=analytics]') as HTMLInputElement).checked,
      marketing: (modal.querySelector('[name=marketing]') as HTMLInputElement).checked,
      functional: (modal.querySelector('[name=functional]') as HTMLInputElement).checked,
    };
    saveAndClose(choices);
  });
}

async function saveAndClose(purposes: ConsentChoices): Promise<void> {
  await fetch('/zaraz/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ purposes }),
  });

  applyConsentToZaraz(purposes);
  document.getElementById('consent-modal')?.remove();
}
```

**Server-side event forwarding with consent check:**

```typescript
type Purpose = 'analytics' | 'marketing' | 'functional';

async function forwardEventIfConsented(
  env: Env,
  uid: string,
  event: string,
  properties: Record<string, unknown>,
  requiredPurpose: Purpose,
): Promise<void> {
  const record = await env.CONSENT_KV.get<ConsentRecord>(
    `consent:${uid}`,
    'json',
  );

  if (!record?.purposes[requiredPurpose]) {
    console.log(`Skipping event ${event}: no consent for ${requiredPurpose}`);
    return;
  }

  await fetch('https://your-domain.com/cdn-cgi/zaraz/t', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: event, properties }),
  });
}
```

**KV namespace setup:**

```bash
wrangler kv namespace create CONSENT_KV
wrangler kv namespace create CONSENT_KV --preview
```

```toml
# wrangler.toml
[[kv_namespaces]]
binding = "CONSENT_KV"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
preview_id = "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy"
```

## Implementation Details

**Zaraz dashboard configuration (per tool):**

In the Zaraz Dashboard, go to Tools, then for each tool assign it to a consent purpose and enable "Block until consent". Tool identifiers map to the purpose keys defined in your Worker. The Zaraz Consent API reads these assignments to know which tools to unblock after `zaraz.consent.set()` is called.

**Consent version management:**

When you add a new consent purpose, increment the `version` field in `ConsentRecord`. On page load, compare `record.version` against the current version constant. If `record.version < CURRENT_VERSION`, re-show the consent modal for the new purpose only.

```typescript
const CURRENT_CONSENT_VERSION = 2;

export async function initConsent(): Promise<void> {
  const res = await fetch('/zaraz/consent');
  const record = await res.json<ConsentRecord>();

  if (record.timestamp > 0 && record.version >= CURRENT_CONSENT_VERSION) {
    applyConsentToZaraz(record.purposes);
    return;
  }

  showConsentModal(record.purposes); // pre-fill existing choices
}
```

## Anti-patterns

- **Relying solely on client-side Zaraz consent API without server-side enforcement.** A determined user can call `zaraz.consent.set('marketing', true)` in DevTools. Server-side KV verification is the authoritative source of truth.
- **Storing consent in `localStorage`.** LocalStorage can be cleared by the browser, is not available in private mode, and cannot be read by Workers. Use a first-party HttpOnly cookie tied to a KV record.
- **One-size-fits-all consent.** GDPR requires per-purpose granularity. Storing a single boolean (`acceptedAll: true`) does not satisfy the granularity requirement.
- **Re-showing the modal on every page load.** Check the existing consent record on page load and only show the modal when `record.timestamp === 0` or the consent version has changed.
- **Forwarding events server-side without checking consent.** Backend-triggered events (order placed, payment processed) must also respect consent. Check KV before forwarding to any analytics destination.

## Gotchas

- **Zaraz consent API is only available after the Zaraz script loads.** Guard all `window.zaraz.consent` calls with a `DOMContentLoaded` or `zaraz:loaded` event listener.
- **`sendQueuedEvents()`** replays events that were fired before consent was set (e.g. a page view triggered immediately on load). Without calling it, the initial page view is lost.
- **KV eventual consistency.** KV reads are eventually consistent across regions. A consent choice set in one region may take up to 60 seconds to propagate globally. For critical paths, use `CONSENT_KV.get(key, { cacheTtl: 0 })` to bypass the cache.
- **Cookie SameSite=Lax** means the UID cookie is sent on top-level navigations but not cross-site sub-requests. This is intentional and correct for a first-party consent cookie.

## Verification

```bash
# Test consent storage
curl -X POST https://your-site.com/zaraz/consent \
  -H 'Content-Type: application/json' \
  -d '{"purposes": {"analytics": true, "marketing": false, "functional": true}}'
# Expect: {"ok": true, "uid": "<uuid>"} with Set-Cookie header

# Read back consent
curl https://your-site.com/zaraz/consent \
  -H 'Cookie: zaraz_uid=<uuid-from-above>'
# Expect: {"purposes": {"analytics": true, "marketing": false, "functional": true}, ...}

# Verify KV entry directly
npx wrangler kv key get --namespace-id=<id> "consent:<uuid>"
```

## Related

- `workers-kv-storage-patterns.md` — KV TTL management and cache strategies
- `workers-cookie-first-party-patterns.md` — secure first-party cookie management
- Cloudflare Zaraz dashboard: Tools -> Consent configuration

## Sources

- https://developers.cloudflare.com/zaraz/consent-management/
- https://developers.cloudflare.com/zaraz/reference/consent-api/
- https://developers.cloudflare.com/kv/
- https://gdpr.eu/cookies/
