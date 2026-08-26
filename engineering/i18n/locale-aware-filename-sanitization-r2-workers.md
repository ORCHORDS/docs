# Locale-Aware Filename Sanitization for R2 Uploads in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Users upload files whose names contain Cyrillic, Arabic, CJK, or emoji characters. R2 accepts
arbitrary UTF-8 keys, but downstream systems — CDNs, signed-URL parsers, email attachments —
choke on raw Unicode object keys. Naively stripping non-ASCII produces silent collisions
("résumé.pdf" and "resume.pdf" become the same key). A locale-aware sanitization pipeline
preserves readability, avoids collisions, and generates safe, predictable R2 object keys.

## Context

The right sanitization strategy depends on the filename's script:
- **Latin with diacritics** (French, German, Polish): NFD decomposition + strip combining marks.
- **Cyrillic / Greek**: transliterate to Latin equivalents.
- **CJK (Chinese, Japanese, Korean)**: transliterate or replace with a stable hash segment.
- **Arabic / Hebrew RTL scripts**: transliterate or hash — embedding RTL text in a key can
  confuse path parsers.
- **Emoji**: strip or replace with a descriptive ASCII slug.

Workers does not ship a full transliteration library; a lightweight lookup table handles the
common cases and a hash-based fallback covers everything else.

---

## NFC Normalization and Diacritic Stripping

```typescript
// sanitize/latin.ts
export function stripDiacritics(input: string): string {
  // NFD decomposes é → e + combining-acute; then strip combining marks (U+0300–U+036F).
  return input
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

// "résumé.pdf" → "resume.pdf"
// "Ångström.png" → "Angstrom.png"
```

---

## Cyrillic Transliteration Table

```typescript
// sanitize/cyrillic.ts
const CYRILLIC: Record<string, string> = {
  а:"a", б:"b", в:"v", г:"g", д:"d", е:"e", ё:"yo", ж:"zh", з:"z",
  и:"i", й:"y", к:"k", л:"l", м:"m", н:"n", о:"o", п:"p", р:"r",
  с:"s", т:"t", у:"u", ф:"f", х:"kh", ц:"ts", ч:"ch", ш:"sh",
  щ:"shch", ъ:"", ы:"y", ь:"", э:"e", ю:"yu", я:"ya",
};

export function transliterateCyrillic(input: string): string {
  return [...input]
    .map(ch => {
      const lower = ch.toLowerCase();
      const t = CYRILLIC[lower];
      if (t === undefined) return ch;
      // Preserve approximate casing.
      return ch === ch.toUpperCase() ? t.toUpperCase() : t;
    })
    .join("");
}

// "Привет мир.txt" → "Privet-mir.txt"  (after further cleanup)
```

---

## CJK and Script Detection with Hash Fallback

For scripts that have no clean romanisation in the browser runtime (CJK, Arabic, Devanagari),
emit a short SHA-1 segment so the key is stable and collision-free.

```typescript
// sanitize/hash.ts
async function shortHash(input: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-1",
    new TextEncoder().encode(input)
  );
  return Array.from(new Uint8Array(buf))
    .slice(0, 4)
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

// Detect whether the string contains a predominantly non-Latin script.
const NON_LATIN_SCRIPT_RE =
  /[؀-ۿऀ-ॿ一-鿿぀-ヿ가-힣]/;

export async function sanitizeSegment(segment: string): Promise<string> {
  if (!NON_LATIN_SCRIPT_RE.test(segment)) return segment;
  const h = await shortHash(segment);
  // Keep first 8 safe ASCII chars of segment for human hint, then append hash.
  const hint = segment.replace(/[^a-zA-Z0-9]/g, "").slice(0, 8) || "file";
  return `${hint}-${h}`;
}
```

---

## Full Sanitization Pipeline

```typescript
// sanitize/index.ts
import { stripDiacritics } from "./latin";
import { transliterateCyrillic } from "./cyrillic";
import { sanitizeSegment } from "./hash";

const MAX_KEY_BYTES = 512;           // R2 object key limit
const MAX_FILENAME_CHARS = 100;

export async function sanitizeFilename(
  raw: string,
  prefix: string = ""          // e.g. "uploads/user-123/"
): Promise<string> {
  // 1. Normalize to NFC first (consistent code points before any transformation).
  let name = raw.normalize("NFC");

  // 2. Split extension.
  const dotIdx = name.lastIndexOf(".");
  const ext = dotIdx > 0 ? name.slice(dotIdx).toLowerCase().replace(/[^.a-z0-9]/g, "") : "";
  const stem = dotIdx > 0 ? name.slice(0, dotIdx) : name;

  // 3. Transliterate Cyrillic.
  let safe = transliterateCyrillic(stem);

  // 4. Strip Latin diacritics.
  safe = stripDiacritics(safe);

  // 5. Handle remaining non-ASCII segments word-by-word.
  const parts = await Promise.all(
    safe.split(/\s+/).map(w => sanitizeSegment(w))
  );
  safe = parts.join("-");

  // 6. Collapse and trim unsafe URL characters.
  safe = safe
    .replace(/[^a-zA-Z0-9\-_]/g, "-")   // replace anything left
    .replace(/-{2,}/g, "-")              // collapse runs of dashes
    .replace(/^-+|-+$/g, "")            // trim leading/trailing dashes
    .slice(0, MAX_FILENAME_CHARS);

  if (!safe) safe = "file";

  const filename = ext ? `${safe}${ext}` : safe;
  const fullKey = `${prefix}${filename}`;

  // 7. Guard against exceeding R2's key byte length.
  const encoded = new TextEncoder().encode(fullKey);
  if (encoded.byteLength > MAX_KEY_BYTES) {
    throw new Error(`R2 key too long: ${encoded.byteLength} bytes`);
  }

  return fullKey;
}
```

---

## Collision Detection via D1

Two different raw names may produce the same sanitized key. Check D1 before writing.

```typescript
// src/upload-handler.ts
async function reserveKey(
  sanitized: string,
  env: { DB: D1Database }
): Promise<string> {
  const existing = await env.DB
    .prepare("SELECT key FROM uploads WHERE key = ?1")
    .bind(sanitized)
    .first();

  if (!existing) return sanitized;

  // Append a short random suffix to break the collision.
  const suffix = Math.random().toString(36).slice(2, 6);
  const dotIdx = sanitized.lastIndexOf(".");
  return dotIdx > 0
    ? `${sanitized.slice(0, dotIdx)}-${suffix}${sanitized.slice(dotIdx)}`
    : `${sanitized}-${suffix}`;
}
```

---

## Anti-patterns

- **Using `encodeURIComponent` as the sole sanitizer**: percent-encoded keys like `%D0%9F%D1%80`
  are valid in R2 but opaque to humans and vary by encoding library at read time.
- **Stripping all non-ASCII blindly**: "документ.pdf" and "договор.pdf" both collapse to ".pdf",
  silently overwriting each other.
- **Relying on the original filename in the public URL**: expose a stable UUID or sanitized key;
  never echo back user-supplied filenames in `Content-Disposition` without sanitization.
- **Skipping NFC before processing**: decomposed strings (NFD) cause Cyrillic/Latin character
  detectors to miss composed code points.

## Gotchas

- R2 keys are case-sensitive; always lower-case the extension but preserve stem case unless you
  intentionally want a uniform scheme.
- The 512-byte limit is measured in UTF-8 bytes, not characters. A full CJK path prefix can
  exhaust the budget before the filename is appended — enforce byte-level accounting.
- `crypto.subtle.digest` in Workers is async; the sanitization pipeline must therefore be async
  end-to-end.

## Verification

```bash
# Unit-test the pipeline locally
npx vitest run sanitize

# Confirm a Cyrillic upload produces the expected key
curl -X PUT https://your-worker.example.com/upload \
  -F "file=@/tmp/Привет.pdf" | jq .key
# Expected: "uploads/Privet.pdf"  (or "Privet-a3f2.pdf" if collision)

# Inspect D1 for duplicate key entries
wrangler d1 execute DB \
  --command "SELECT key, COUNT(*) n FROM uploads GROUP BY key HAVING n > 1;"
```

## Related

- `locale-aware-csv-export-workers-d1.md`
- `unicode-normalization-nfc-nfd.md`
- `transliteration-vs-translation-2026.md`
- `r2-font-subsetting-multi-script-pipeline-2026.md`

## Sources

- R2 Object key naming — https://developers.cloudflare.com/r2/buckets/object-keys/
- Unicode NFC/NFD — https://unicode.org/reports/tr15/
- Unicode Transliteration Guidelines — https://unicode.org/cldr/charts/latest/transforms/index.html
- RFC 8187 — Indicating Character Encoding in HTTP Header Fields
