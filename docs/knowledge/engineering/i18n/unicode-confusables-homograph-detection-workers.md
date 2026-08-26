# Unicode Confusables and Homograph Attack Detection in Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Users register usernames like `pаypal` (Cyrillic `а`) alongside `paypal` (Latin `a`) and the
two strings compare as different in a database UNIQUE check, creating a homograph spoofing
opportunity. Similarly, phishing URLs use mixed-script domain names that render identically
to legitimate ones in most fonts. The example project platform must detect and reject or normalise
confusable inputs at the Workers edge — before the record ever reaches D1 or KV.

## Context

Unicode defines a **confusable** as a character or sequence that is visually indistinguishable
from another under common fonts. The Unicode Security Mechanisms (UTS #39) dataset
(`confusables.txt`) maps each source character to a **skeleton form** — a normalised
representative sequence — so two strings are confusable if and only if their skeletons are
identical. V8 (used by the Workers runtime) does not expose this dataset natively; it must be
embedded or queried from a KV-cached copy. The BCP 47 locale tag does not affect confusable
analysis — the dataset is script-level, not locale-level.

---

## 1. Skeleton normalisation algorithm (UTS #39 §4)

```typescript
// Pseudo-implementation matching UTS #39 skeleton algorithm
// skeleton(s) = NFD(map each char to its confusable prototype, then NFC)
import { confusablesMap } from './confusables-map'; // pre-built compact Map<number, string>

function toSkeleton(input: string): string {
  // Step 1: map each code point to its prototype sequence
  const mapped = [...input]
    .map(ch => confusablesMap.get(ch.codePointAt(0)!) ?? ch)
    .join('');
  // Step 2: apply NFD then NFC (removes diacritic ordering ambiguity)
  return mapped.normalize('NFD').normalize('NFC');
}

export function areConfusable(a: string, b: string): boolean {
  return toSkeleton(a) === toSkeleton(b);
}
```

The confusables map (`confusables.txt`, ~5 000 entries, ~40 KB gzipped) is loaded once per
isolate from KV and cached in a module-level `Map<number, string>`.

---

## 2. Loading the confusables dataset from KV

```typescript
// confusables-loader.ts
export interface Env {
  I18N_DATA: KVNamespace;
}

let cachedMap: Map<number, string> | null = null;

export async function getConfusablesMap(env: Env): Promise<Map<number, string>> {
  if (cachedMap) return cachedMap;

  const raw = await env.I18N_DATA.get('unicode:confusables:v15', { type: 'json' }) as
    Record<string, string> | null;

  if (!raw) throw new Error('Confusables dataset missing from KV');

  cachedMap = new Map(
    Object.entries(raw).map(([cp, proto]) => [parseInt(cp, 10), proto])
  );
  return cachedMap;
}
```

Upload the dataset during your deploy pipeline:

```bash
# build/upload-confusables.ts (run as a Wrangler pre-deploy script)
npx wrangler kv key put \
  --namespace-id=$KV_ID \
  unicode:confusables:v15 \
  "$(node scripts/parse-confusables-txt.js)" \
  --expiration-ttl=2592000   # 30 days; refresh on Unicode point releases
```

---

## 3. Username registration guard in a Workers handler

```typescript
// src/handlers/register.ts
import { getConfusablesMap } from '../confusables-loader';
import { toSkeleton } from '../confusables-algo';

export async function handleRegister(req: Request, env: Env): Promise<Response> {
  const { username } = await req.json<{ username: string }>();

  // 1. Basic length / charset validation first
  if (!/^[\p{L}\p{N}_.-]{2,30}$/u.test(username)) {
    return Response.json({ error: 'invalid_username' }, { status: 400 });
  }

  const map = await getConfusablesMap(env);
  const skeleton = toSkeleton(username); // uses map

  // 2. Check the skeleton against existing skeletons stored in D1
  const existing = await env.DB.prepare(
    'SELECT username FROM users WHERE username_skeleton = ? LIMIT 1'
  ).bind(skeleton).first<{ username: string }>();

  if (existing) {
    return Response.json(
      { error: 'confusable_username', existing: existing.username },
      { status: 409 }
    );
  }

  // 3. Persist both the display form and the skeleton
  await env.DB.prepare(
    'INSERT INTO users (username, username_skeleton) VALUES (?, ?)'
  ).bind(username, skeleton).run();

  return Response.json({ ok: true }, { status: 201 });
}
```

D1 schema addition:

```sql
ALTER TABLE users ADD COLUMN username_skeleton TEXT GENERATED ALWAYS AS
  (username_skeleton_fn(username)) VIRTUAL;   -- or stored as a real column
CREATE UNIQUE INDEX idx_users_skeleton ON users(username_skeleton);
```

Because D1/SQLite has no built-in skeleton function, store the skeleton as a real TEXT column
computed in the Workers layer and indexed with UNIQUE.

---

## 4. Mixed-script detection (single-script rule)

```typescript
// Detect mixed scripts — a hallmark of homograph attacks
const SCRIPT_RE = /\p{Script=Latin}|\p{Script=Cyrillic}|\p{Script=Greek}/gu;

function extractScripts(s: string): Set<string> {
  const scripts = new Set<string>();
  for (const match of s.matchAll(/\p{Script=(\w+)}/dgu)) {
    scripts.add(match[1]);
  }
  return scripts;
}

// Simplified version using Intl locale extensions (V8 supports Unicode property escapes)
function isMixedScript(s: string): boolean {
  const latin   = /\p{Script=Latin}/u.test(s);
  const cyrillic = /\p{Script=Cyrillic}/u.test(s);
  const greek   = /\p{Script=Greek}/u.test(s);
  // Allowed combinations: Han + Hiragana + Katakana (CJK), Han + Bopomofo, etc.
  const confusableCombo = [latin, cyrillic, greek].filter(Boolean).length > 1;
  return confusableCombo;
}

if (isMixedScript(username)) {
  return Response.json({ error: 'mixed_script_username' }, { status: 400 });
}
```

---

## 5. IDN / URL homograph sanitisation in HTMLRewriter

```typescript
// Rewrite anchor hrefs to expose suspicious punycode rendering
export class HomographLinkRewriter implements HTMLRewriterElementContentHandlers {
  element(el: Element) {
    const href = el.getAttribute('href') ?? '';
    try {
      const url = new URL(href);
      // URL constructor auto-converts IDN to punycode on Workers V8
      const punyHostname = url.hostname; // 'xn--pypl-toc0a.com' for Cyrillic paypal
      const displayHostname = el.getAttribute('data-display-host') ?? url.hostname;
      if (punyHostname !== displayHostname.toLowerCase()) {
        el.setAttribute('data-suspicious', 'homograph');
        el.setAttribute('title', `Warning: domain encodes as ${punyHostname}`);
      }
    } catch { /* relative URLs — skip */ }
  }
}

// In your Worker fetch handler:
return new HTMLRewriter()
  .on('a[href^="http"]', new HomographLinkRewriter())
  .transform(response);
```

---

## Anti-patterns

- **Comparing raw Unicode strings for uniqueness** — `pаypal` and `paypal` pass UNIQUE
  constraints and differ in `===` but are visually indistinguishable.
- **Normalising with NFC/NFD only** — Canonical normalisation does not collapse cross-script
  confusables; the full skeleton algorithm is required.
- **Blocking all non-ASCII usernames** — Overly restrictive; disenfranchises most of the
  world's users. Skeleton-based deduplication allows `الرشيد` without conflicting with ASCII.
- **Fetching `confusables.txt` at request time** — Too slow (~150 KB raw). Pre-parse and
  store in KV; load once per isolate warm-up.

## Gotchas

- **Unicode version drift** — The confusables dataset is versioned. Pin the dataset version
  in KV (`unicode:confusables:v15`) and update it when Workers V8 upgrades its Unicode version
  (check `Intl.supportedValuesOf('calendar')` regex for the Unicode base version heuristic).
- **Emoji and ZWJ sequences** — Emoji confusables are sparse but exist (🄰 vs A). The UTS #39
  dataset covers them; ensure your code point iterator handles surrogate pairs via
  `[...string]` or `String.prototype.codePointAt`, not `charCodeAt`.
- **Skeleton is not a display form** — Never show the skeleton to the user; it is an internal
  index key. Always display the original (validated) input.
- **Allowed scripts per locale** — Some scripts legitimately mix (Han + Hiragana in Japanese).
  Apply single-script restriction only where it makes sense (Latin-script brand names,
  usernames on a platform serving a single-script market).

## Verification

```typescript
// Unit tests
import { areConfusable, toSkeleton } from './confusables-algo';

Deno.test('Latin a vs Cyrillic а are confusable', () => {
  assertEquals(areConfusable('paypal', 'pаypal'), true);
});
Deno.test('Different legitimate strings not confusable', () => {
  assertEquals(areConfusable('alice', 'bob'), false);
});
Deno.test('Skeleton is stable', () => {
  // Applying toSkeleton twice must be idempotent
  const once = toSkeleton('pаypal');
  const twice = toSkeleton(once);
  assertEquals(once, twice);
});
```

Run with: `npx vitest run src/confusables-algo.test.ts`

## Related

- `precis-internationalized-username-password-profiles.md`
- `bcp47-language-tag-syntax.md`
- `unicode-identifier-status-and-restriction-levels.md`
- `unicode-identifier-profile-versioning-uax31.md`
- `idn-punycode-internationalized-email.md`

## Sources

- UTS #39 Unicode Security Mechanisms: https://unicode.org/reports/tr39/
- Unicode Confusables Data: https://unicode.org/Public/security/latest/confusables.txt
- UAX #31 Unicode Identifier and Pattern Syntax: https://unicode.org/reports/tr31/
- ICANN IDN Guidelines: https://www.icann.org/resources/pages/idn-guidelines-2003-06-20-en
- Cloudflare Workers V8 Unicode property escapes: https://developers.cloudflare.com/workers/runtime-apis/web-standards/
