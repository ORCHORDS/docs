# Automatic Language Detection Using Workers AI with D1 Caching

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

You receive arbitrary user-submitted text and need to detect its language at the edge so you can route requests to the correct locale handler, without incurring AI inference latency on every request and without maintaining a separate language-detection service.

## Context

Workers AI provides access to LLMs inside the Workers runtime. Language detection is framed as a classification prompt sent to `@cf/meta/llama-3.1-8b-instruct`. To avoid re-running inference on identical text, results are cached in a D1 table keyed by the SHA-256 hash of the input. When AI confidence is below a threshold, the implementation falls back to parsing the `Accept-Language` request header.

---

## Core Implementation

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
}

interface DetectionResult {
  lang: string;       // BCP 47 tag, e.g. "fr", "zh-Hant"
  confidence: number; // 0–1
  source: "ai" | "cache" | "header";
}

const CONFIDENCE_THRESHOLD = 0.75;

/** SHA-256 hex digest of a string (Web Crypto, available in Workers). */
async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text)
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Check D1 cache for a previously detected language. */
async function getCached(
  db: D1Database,
  hash: string
): Promise<{ detected_lang: string; confidence: number } | null> {
  const row = await db
    .prepare(
      "SELECT detected_lang, confidence FROM language_cache WHERE text_hash = ? LIMIT 1"
    )
    .bind(hash)
    .first<{ detected_lang: string; confidence: number }>();
  return row ?? null;
}

/** Persist a detection result to D1. */
async function putCached(
  db: D1Database,
  hash: string,
  lang: string,
  confidence: number
): Promise<void> {
  await db
    .prepare(
      `INSERT OR REPLACE INTO language_cache (text_hash, detected_lang, confidence, cached_at)
       VALUES (?, ?, ?, datetime('now'))`
    )
    .bind(hash, lang, confidence)
    .run();
}

/** Call Workers AI to detect language. Returns lang tag and confidence 0-1. */
async function detectWithAI(
  ai: Ai,
  text: string
): Promise<{ lang: string; confidence: number }> {
  const prompt = [
    "Identify the BCP-47 language tag of the following text.",
    "Reply with JSON only: {\"lang\": \"<tag>\", \"confidence\": <0-1>}.",
    "Text: " + text.slice(0, 400), // limit input tokens
  ].join("\n");

  const response = (await ai.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [{ role: "user", content: prompt }],
    max_tokens: 32,
  })) as { response: string };

  try {
    return JSON.parse(response.response.trim());
  } catch {
    return { lang: "en", confidence: 0 };
  }
}

/** Parse Accept-Language header and return the highest-priority tag. */
function parseAcceptLanguage(header: string | null): string {
  if (!header) return "en";
  return (
    header
      .split(",")
      .map((part) => {
        const [tag, q = "q=1"] = part.trim().split(";");
        return { tag: tag.trim(), q: parseFloat(q.replace("q=", "")) };
      })
      .sort((a, b) => b.q - a.q)[0]?.tag ?? "en"
  );
}

/** Main detection entry point. */
export async function detectLanguage(
  text: string,
  request: Request,
  env: Env
): Promise<DetectionResult> {
  const hash = await sha256(text);

  const cached = await getCached(env.DB, hash);
  if (cached) {
    return { lang: cached.detected_lang, confidence: cached.confidence, source: "cache" };
  }

  const { lang, confidence } = await detectWithAI(env.AI, text);

  if (confidence >= CONFIDENCE_THRESHOLD) {
    await putCached(env.DB, hash, lang, confidence);
    return { lang, confidence, source: "ai" };
  }

  // Fall back to Accept-Language header
  const fallback = parseAcceptLanguage(request.headers.get("Accept-Language"));
  return { lang: fallback, confidence: 0, source: "header" };
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.text();
    const result = await detectLanguage(body, request, env);
    return Response.json(result);
  },
};
```

---

## D1 Schema

```sql
CREATE TABLE IF NOT EXISTS language_cache (
  text_hash    TEXT PRIMARY KEY,
  detected_lang TEXT NOT NULL,
  confidence   REAL NOT NULL,
  cached_at    TEXT NOT NULL
);

-- Optional: purge stale entries older than 30 days
CREATE INDEX IF NOT EXISTS idx_lang_cache_cached_at ON language_cache(cached_at);
```

Run via `wrangler d1 execute <DB_NAME> --file=schema.sql`.

---

## Routing by Detected Language

```typescript
const localeHandlers: Record<string, (req: Request, env: Env) => Promise<Response>> = {
  fr: handleFrench,
  de: handleGerman,
  ja: handleJapanese,
};

const { lang } = await detectLanguage(body, request, env);
const handler = localeHandlers[lang] ?? handleDefault;
return handler(request, env);
```

---

## Cache Eviction

Add a scheduled Worker trigger to delete entries older than 30 days:

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      "DELETE FROM language_cache WHERE cached_at < datetime('now', '-30 days')"
    ).run();
  },
};
```

---

## Anti-patterns

- Sending the full request body (potentially megabytes) to the AI model — always truncate input to a representative prefix (400 characters is sufficient for language detection).
- Caching by raw text string — use a hash to keep KV/D1 keys short and to avoid storing PII as cache keys.
- Trusting AI confidence of `0` — the JSON parse fallback returns `confidence: 0`; always check the threshold before caching.
- Calling AI on every request regardless of `Accept-Language` — for most users the header is sufficient; only invoke AI when the header is absent or `*`.

---

## Gotchas

- **Model JSON compliance**: `llama-3.1-8b-instruct` does not guarantee valid JSON output. Wrap the parse in try/catch and handle the failure path.
- **D1 write latency**: D1 writes are synchronous by default in Workers. For write-heavy caches, consider wrapping `putCached` in `ctx.waitUntil()` to avoid blocking the response.
- **Text too short**: Single words or two-character inputs produce unreliable language detection regardless of model. Add a minimum-length guard (e.g., skip AI detection for `text.length < 20`).
- **BCP 47 tag normalisation**: The model may return `"zh-cn"` (lowercase) or `"zh_CN"` (underscore). Normalise with `Intl.getCanonicalLocales()` before storage.

---

## Verification

```bash
# Detect French
curl -X POST https://your-worker.workers.dev/ \
  -d "Bonjour, comment allez-vous aujourd'hui?"
# Expected: { lang: "fr", confidence: 0.95, source: "ai" }

# Second call should hit cache
curl -X POST https://your-worker.workers.dev/ \
  -d "Bonjour, comment allez-vous aujourd'hui?"
# Expected: { lang: "fr", confidence: 0.95, source: "cache" }
```

---

## Related

- `locale-fallback-chain-kv-workers.md`
- `intl-segmenter-text-tokenization-workers.md`
- `unicode-normalization-nfc-nfd-workers-text.md`

## Sources

- Cloudflare Workers AI models — https://developers.cloudflare.com/workers-ai/models/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- `Accept-Language` header — https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Language
