# Email Personalization Merge Tags with Cloudflare Workers and KV

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Transactional and lifecycle emails need per-recipient variable substitution — first name, account tier, dynamic discount codes, locale-specific content — resolved at send time without per-send database queries. Cloudflare KV provides sub-millisecond read latency for merge-tag data that changes infrequently, while the Worker assembles the final message before handing it to the ESP.

---

## Context

The merge-tag pipeline works in three layers:

1. **KV profile store** — contact attributes keyed by email address or contact ID; written by an account service, read by the email Worker at send time.
2. **Template store** — HTML/text templates stored in KV (or R2 for large templates) with `{{tag}}` placeholders.
3. **Merge engine** — a lightweight Worker-side substitutor that resolves tags, falls back gracefully, and encodes HTML entities.

KV is chosen over D1 for this read path because: (a) KV edges are globally distributed and serve sub-millisecond reads; (b) contact profiles are write-once-read-many; (c) the merge step is latency-critical when inside a send loop.

---

## KV Profile Schema

Key format: `contact:${contactId}` or `profile:${email}`

```typescript
// Stored as JSON in KV
interface ContactProfile {
  contactId: string;
  email: string;
  firstName: string;
  lastName: string;
  locale: string;               // 'en-US' | 'fr-FR' | etc.
  accountTier: 'free' | 'pro' | 'enterprise';
  companyName?: string;
  customAttributes: Record<string, string | number | boolean>;
  updatedAt: number;
}
```

Write side (account service → KV via Workers API):

```typescript
// src/profile-writer.ts
export async function upsertProfile(
  env: Env,
  profile: ContactProfile
): Promise<void> {
  const key = `contact:${profile.contactId}`;
  await env.CONTACT_KV.put(key, JSON.stringify(profile), {
    expirationTtl: 60 * 60 * 24 * 365, // 1 year TTL; refresh on login
    metadata: { email: profile.email, updatedAt: profile.updatedAt },
  });

  // Secondary index: email → contactId for inbound lookup
  await env.CONTACT_KV.put(
    `email:${profile.email.toLowerCase()}`,
    profile.contactId,
    { expirationTtl: 60 * 60 * 24 * 365 }
  );
}
```

---

## Template Storage

```typescript
// src/template-loader.ts
interface EmailTemplate {
  templateId: string;
  subject: string;             // May contain merge tags: "Hello {{firstName}}"
  htmlBody: string;
  textBody: string;
  version: number;
}

export async function loadTemplate(
  env: Env,
  templateId: string
): Promise<EmailTemplate | null> {
  const raw = await env.TEMPLATE_KV.get(`tpl:${templateId}`, 'json');
  return raw as EmailTemplate | null;
}
```

---

## Merge Engine

```typescript
// src/merge-engine.ts

const TAG_PATTERN = /\{\{([a-zA-Z0-9_.]+)\}\}/g;

export interface MergeContext {
  profile: ContactProfile;
  /** Extra one-off values: discount codes, expiry dates, etc. */
  extras?: Record<string, string | number>;
  /** Fallback value when a tag is missing. Default: empty string. */
  fallback?: string;
}

/**
 * Resolve all {{tag}} placeholders in a template string.
 * Dots in tag names traverse nested paths: {{customAttributes.plan}}
 */
export function mergeTags(
  template: string,
  ctx: MergeContext,
  encodeHtml = true
): string {
  return template.replace(TAG_PATTERN, (_match, tag) => {
    const value = resolveTag(tag, ctx);
    return encodeHtml ? htmlEncode(String(value)) : String(value);
  });
}

function resolveTag(tag: string, ctx: MergeContext): string | number {
  const { profile, extras, fallback = '' } = ctx;

  // Check extras first (highest priority: per-send dynamic values)
  if (extras && tag in extras) return extras[tag];

  // Traverse nested path on profile
  const parts = tag.split('.');
  let cursor: unknown = profile;
  for (const part of parts) {
    if (cursor == null || typeof cursor !== 'object') return fallback;
    cursor = (cursor as Record<string, unknown>)[part];
  }

  return cursor != null ? String(cursor) : fallback;
}

function htmlEncode(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Plain-text version — no HTML encoding needed */
export function mergeTagsText(template: string, ctx: MergeContext): string {
  return mergeTags(template, ctx, false);
}
```

---

## Send Pipeline Integration

```typescript
// src/send.ts
import { loadTemplate } from './template-loader';
import { mergeTags, mergeTagsText, MergeContext } from './merge-engine';

interface SendRequest {
  contactId: string;
  templateId: string;
  extras?: Record<string, string | number>;
}

export async function sendTransactional(
  env: Env,
  req: SendRequest
): Promise<void> {
  // Parallel fetch: profile + template
  const [profileRaw, template] = await Promise.all([
    env.CONTACT_KV.get(`contact:${req.contactId}`, 'json'),
    loadTemplate(env, req.templateId),
  ]);

  if (!profileRaw) throw new Error(`Profile not found: ${req.contactId}`);
  if (!template)  throw new Error(`Template not found: ${req.templateId}`);

  const profile = profileRaw as ContactProfile;
  const ctx: MergeContext = {
    profile,
    extras: req.extras,
    fallback: '',
  };

  const subject  = mergeTagsText(template.subject,  ctx);
  const htmlBody = mergeTags(template.htmlBody, ctx, true);  // HTML-encoded
  const textBody = mergeTagsText(template.textBody,  ctx);

  await dispatchToEsp(env, {
    to:      profile.email,
    subject,
    html:    htmlBody,
    text:    textBody,
    headers: {
      'X-Contact-ID': req.contactId,
      'X-Template-ID': `${req.templateId}:v${template.version}`,
    },
  });
}
```

---

## Locale-aware Tag Rendering

```typescript
// src/locale-tags.ts — extend MergeContext for date/currency formatting
export function formatMergeValue(
  key: string,
  rawValue: string | number,
  locale: string
): string {
  // Detect numeric formatting hints in key name
  if (key.endsWith('_currency') && typeof rawValue === 'number') {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency: 'USD',
    }).format(rawValue);
  }
  if (key.endsWith('_date') && typeof rawValue === 'number') {
    return new Intl.DateTimeFormat(locale, {
      dateStyle: 'long',
    }).format(new Date(rawValue));
  }
  return String(rawValue);
}
```

---

## Bulk Profile Refresh Cron

```typescript
// src/profile-refresh.ts — scheduled cron, syncs profiles changed in last hour
export async function refreshStaleProfiles(env: Env): Promise<void> {
  const since = Date.now() - 60 * 60 * 1000;

  // Fetch changed contacts from your source-of-truth DB
  const changed = await fetchContactsChangedSince(env, since);

  // Write to KV in parallel batches of 50
  const BATCH = 50;
  for (let i = 0; i < changed.length; i += BATCH) {
    await Promise.all(
      changed.slice(i, i + BATCH).map(profile => upsertProfile(env, profile))
    );
  }
}
```

---

## Anti-patterns

- **Fetching profiles from D1 inside a tight send loop** — D1 has ~1–3 ms regional latency; KV edges serve in <0.5 ms and handle 100k+ RPS without query planning overhead.
- **Using `eval()` or template literals with raw user data** — always use a tag-pattern replacement function; never interpolate untrusted profile strings into JS template literals.
- **HTML-encoding the text/plain part** — `&amp;` in a plain-text email body is the literal string, not an ampersand; only encode for HTML body.
- **Missing fallbacks** — a blank first name renders "Hello ," in subject lines; always define a fallback (`'there'`, `'valued customer'`) in the MergeContext.
- **Storing large profile blobs in KV** — KV values are limited to 25 MB but large values increase read latency; keep profiles under 4 KB; move bulky assets (avatar URLs, preference arrays) to D1.

---

## Gotchas

- KV consistency is eventual across regions; a profile written by the account service may take up to 60 seconds to propagate to all edge nodes. For sign-up emails sent immediately after registration, write the profile to KV and then delay the email Worker trigger by 2–5 seconds.
- KV list operations (`list()`) are slow and do not substitute for D1 queries; never list KV keys to find contacts — resolve by known key only.
- `customAttributes` keys with dots (e.g. `billing.plan`) conflict with the path-traversal resolver; sanitize custom attribute keys by replacing `.` with `_` on write.
- Workers KV `get()` returns `null` for missing keys, not an exception; handle null profiles gracefully or the merge step will throw.

---

## Verification

```bash
# Write a test profile
wrangler kv key put --binding CONTACT_KV \
  "contact:test_001" \
  '{"contactId":"test_001","email":"alice@example.com","firstName":"Alice","lastName":"Smith","locale":"en-US","accountTier":"pro","customAttributes":{"plan":"annual"},"updatedAt":1761264000000}'

# Read it back
wrangler kv key get --binding CONTACT_KV "contact:test_001"

# Trigger a send
curl -X POST https://workers.example.com/send \
  -H "Content-Type: application/json" \
  -d '{"contactId":"test_001","templateId":"welcome","extras":{"discount_code":"SAVE20"}}'

# Inspect rendered output in Worker logs
wrangler tail --format=pretty
```

---

## Related

- `email-personalization-patterns.md`
- `email-transactional-template-personalization-r2-workers.md`
- `email-template-versioning-ab-testing-r2.md`
- `email-dynamic-content.md`
- `liquid-template-email.md`
- `handlebars-email-templates.md`

---

## Sources

- Cloudflare KV read consistency: https://developers.cloudflare.com/kv/reference/how-kv-works/
- Cloudflare KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Intl.NumberFormat (Workers V8): https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat
- RFC 6068 mailto: URI merge guidance: https://www.rfc-editor.org/rfc/rfc6068
