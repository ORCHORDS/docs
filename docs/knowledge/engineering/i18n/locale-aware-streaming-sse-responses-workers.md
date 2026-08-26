# Locale-Aware Streaming SSE Responses in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Streaming Server-Sent Events (SSE) responses from a Cloudflare Worker that contain numbers, dates,
currency amounts, or translatable strings render in the server's default locale instead of the
viewer's, because locale context is discarded before the stream is assembled.

## Context
Workers AI, AI Gateway, and any long-running generation task may emit partial results as SSE chunks.
When those chunks contain locale-sensitive values — formatted numbers in financial dashboards, relative
timestamps in activity feeds, or translated UI labels in chat interfaces — each chunk must be
formatted consistently using the viewer's resolved locale. The `Intl` APIs are fully available in the
Workers runtime; the challenge is threading the locale through `TransformStream` pipeline stages
without re-resolving it on every chunk.

## Resolving and Pinning Locale for the Stream Lifetime

Resolve locale once from the request, then close it into the `TransformStream` constructor. This
avoids repeated parsing and ensures every chunk in the stream uses an identical locale string.

```typescript
// locale-stream.ts
import { detectLocale } from "./locale";

export function createLocaleAwareStream(
  source: ReadableStream<Uint8Array>,
  request: Request
): ReadableStream<Uint8Array> {
  const locale = detectLocale(request);
  const numberFmt = new Intl.NumberFormat(locale, { style: "decimal", maximumFractionDigits: 2 });
  const dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      const text = decoder.decode(chunk, { stream: true });
      const formatted = formatSseChunk(text, numberFmt, dateFmt);
      controller.enqueue(encoder.encode(formatted));
    },
    flush(controller) {
      // Flush any remaining buffered bytes from the decoder
      const remaining = decoder.decode();
      if (remaining) {
        controller.enqueue(encoder.encode(remaining));
      }
    },
  });

  source.pipeTo(writable);
  return readable;
}
```

## Formatting Values Inside SSE Chunks

SSE data lines carry JSON payloads in practice. Parse, format locale-sensitive fields, and
re-serialise. Protect against partial JSON at chunk boundaries by buffering until a complete line.

```typescript
// sse-formatter.ts
export function formatSseChunk(
  raw: string,
  numberFmt: Intl.NumberFormat,
  dateFmt: Intl.DateTimeFormat
): string {
  return raw
    .split("\n")
    .map(line => {
      if (!line.startsWith("data: ")) return line;
      try {
        const payload = JSON.parse(line.slice(6));
        if (typeof payload.amount === "number") {
          payload.amount_display = numberFmt.format(payload.amount);
        }
        if (typeof payload.ts === "number") {
          payload.ts_display = dateFmt.format(new Date(payload.ts));
        }
        return `data: ${JSON.stringify(payload)}`;
      } catch {
        // Not valid JSON — pass through unchanged (e.g. keep-alive comments)
        return line;
      }
    })
    .join("\n");
}
```

## Buffering Across Chunk Boundaries

`TransformStream` chunks may arrive mid-JSON or mid-UTF-8 multibyte sequence. Use a line buffer so
SSE event boundaries are respected before attempting to parse.

```typescript
// line-buffer.ts
export class SseLineBuffer {
  private buf = "";

  push(chunk: string): string[] {
    this.buf += chunk;
    const lines = this.buf.split("\n");
    this.buf = lines.pop() ?? "";  // keep incomplete last line
    return lines;
  }

  flush(): string[] {
    const remaining = this.buf ? [this.buf] : [];
    this.buf = "";
    return remaining;
  }
}
```

```typescript
// locale-stream-buffered.ts
export function createBufferedLocaleStream(
  source: ReadableStream<Uint8Array>,
  request: Request
): ReadableStream<Uint8Array> {
  const locale = detectLocale(request);
  const numberFmt = new Intl.NumberFormat(locale);
  const dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: "short" });
  const lineBuf = new SseLineBuffer();
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  const { readable, writable } = new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      const text = decoder.decode(chunk, { stream: true });
      const lines = lineBuf.push(text);
      const formatted = lines.map(l => formatSseLine(l, numberFmt, dateFmt)).join("\n") + "\n";
      controller.enqueue(encoder.encode(formatted));
    },
    flush(controller) {
      const lines = lineBuf.flush();
      if (lines.length) {
        const formatted = lines.map(l => formatSseLine(l, numberFmt, dateFmt)).join("\n");
        controller.enqueue(encoder.encode(formatted));
      }
    },
  });

  source.pipeTo(writable);
  return readable;
}

function formatSseLine(
  line: string,
  nf: Intl.NumberFormat,
  df: Intl.DateTimeFormat
): string {
  if (!line.startsWith("data: ")) return line;
  try {
    const p = JSON.parse(line.slice(6));
    if (typeof p.value === "number") p.display = nf.format(p.value);
    if (typeof p.ts === "number") p.date = df.format(new Date(p.ts));
    return `data: ${JSON.stringify(p)}`;
  } catch {
    return line;
  }
}
```

## RTL Markers for Streamed Text Segments

For Arabic, Hebrew, and Persian locales, streamed text must be wrapped in Unicode directional
isolates (U+2066 / U+2069) so the client renders mixed-direction content correctly without a full
DOM reflow.

```typescript
// rtl-wrap.ts
const RTL_LOCALES = new Set(["ar", "he", "fa", "ur", "yi", "dv"]);

export function wrapRtlIfNeeded(text: string, locale: string): string {
  const lang = locale.split("-")[0].toLowerCase();
  if (!RTL_LOCALES.has(lang)) return text;
  // First Strong Isolate + content + Pop Directional Isolate
  return `⁦${text}⁩`;
}
```

## Worker Fetch Handler: Composing the Pipeline

```typescript
// worker.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const upstream = await fetch(new Request(env.AI_GATEWAY_URL, request));
    if (!upstream.body) return upstream;

    const ct = upstream.headers.get("content-type") ?? "";
    if (!ct.includes("text/event-stream")) return upstream;

    const locale = detectLocale(request);
    const transformed = createBufferedLocaleStream(upstream.body, request);

    return new Response(transformed, {
      status: upstream.status,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
        "Content-Language": locale,
      },
    });
  },
};
```

## Anti-patterns
- Constructing `Intl.NumberFormat` or `Intl.DateTimeFormat` inside `transform()` — creates a new
  object per chunk; construct once in the outer scope
- Using `TextDecoder` without `{ stream: true }` in `transform()` — corrupts multi-byte codepoints
  split across chunk boundaries
- Sending SSE chunks smaller than one full `data:` line — forces the client to buffer and defeats
  streaming latency goals
- Formatting all numbers even when they are IDs or phone numbers — gate on semantic field names

## Gotchas
- Workers have a 128 MB memory limit; long-lived SSE streams accumulate backpressure if the client
  reads slowly — set a `QueuingStrategy` with `highWaterMark: 1` on the transform
- `Intl.DateTimeFormat` in the Workers runtime does not load IANA timezone data on-demand; test
  with non-UTC timezones before deploying
- SSE requires `Transfer-Encoding: chunked`; Cloudflare sets this automatically for streaming
  `Response` bodies — do not set it manually
- `Content-Language` on an SSE stream is informational; clients must negotiate locale separately
  via the initial request

## Verification
1. Connect to the Worker with `curl -N` and pipe output through `jq`; assert every `amount_display`
   field uses the decimal separator for the requested locale.
2. Request with `Accept-Language: ar` and assert `⁦` and `⁩` wrap text content fields.
3. Send a synthetic stream with a multibyte CJK character split across two chunks; assert the output
   does not contain the UTF-8 replacement character (U+FFFD).
4. Measure time-to-first-byte with and without the transform — overhead should be < 5 ms.

## Related
- `/documentation/docs/policies/i18n/intl-api-workers-edge-formatting.md`
- `/documentation/docs/policies/i18n/rtl-bidi-handling.md`
- `/documentation/docs/policies/i18n/locale-negotiation-accept-language.md`
- `/documentation/docs/policies/i18n/currency-formatting-cloudflare-workers-intl-numberformat.md`
- `/documentation/docs/policies/i18n/date-time-timezone-workers-edge-formatting.md`

## Sources
- Workers Streams API: https://developers.cloudflare.com/workers/runtime-apis/streams/
- WHATWG Streams `TransformStream`: https://streams.spec.whatwg.org/#transform-stream
- SSE specification: https://html.spec.whatwg.org/multipage/server-sent-events.html
- Unicode Bidirectional Isolates: https://www.unicode.org/reports/tr9/#Explicit_Directional_Isolates
