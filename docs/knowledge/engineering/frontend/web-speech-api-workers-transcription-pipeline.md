# Web Speech API + Cloudflare Workers Transcription Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

**Symptom / Use-case:** You want browser-native speech recognition or synthesis in a web app backed by Cloudflare Workers — storing transcripts in D1, rate-limiting by session via KV, or post-processing audio via Workers AI — without shipping a full third-party SDK bundle.

**Context:** The Web Speech API (`SpeechRecognition` / `SpeechSynthesis`) is available in all Chromium browsers (Firefox still behind a flag as of 2026). Recognition runs on the browser's cloud backend (Google for Chrome); synthesis runs locally. Workers intercept transcript payloads for persistence, moderation, and analytics without touching the audio stream itself.

---

## Feature Detection and Vendor Prefix

```typescript
// lib/speech.ts
const SpeechRecognition =
  window.SpeechRecognition ?? (window as any).webkitSpeechRecognition;

if (!SpeechRecognition) {
  throw new DOMException('SpeechRecognition unavailable', 'NotSupportedError');
}

export function createRecognizer(lang = 'en-US'): SpeechRecognition {
  const rec = new SpeechRecognition();
  rec.lang = lang;
  rec.interimResults = true;   // stream partial results
  rec.maxAlternatives = 1;
  rec.continuous = true;       // keep mic open across pauses
  return rec;
}
```

## Streaming Interim + Final Results to the UI

```typescript
// components/TranscriptBox.tsx  (React 19)
import { useState, useRef, useTransition } from 'react';
import { createRecognizer } from '@/lib/speech';

export function TranscriptBox({ sessionId }: { sessionId: string }) {
  const [interim, setInterim] = useState('');
  const [finals, setFinals] = useState<string[]>([]);
  const [, startTransition] = useTransition();
  const recRef = useRef<SpeechRecognition | null>(null);

  function start() {
    const rec = createRecognizer();
    recRef.current = rec;

    rec.onresult = (e) => {
      let interimText = '';
      for (const result of Array.from(e.results)) {
        if (result.isFinal) {
          const transcript = result[0].transcript.trim();
          startTransition(() => setFinals((f) => [...f, transcript]));
          persistTranscript(sessionId, transcript);   // fire-and-forget
        } else {
          interimText += result[0].transcript;
        }
      }
      setInterim(interimText);
    };

    rec.onerror = (e) => console.error('SpeechRecognition error', e.error);
    rec.start();
  }

  return (
    <div>
      <button onClick={start}>Start</button>
      <button onClick={() => recRef.current?.stop()}>Stop</button>
      <p style={{ color: 'gray' }}>{interim}</p>
      {finals.map((t, i) => <p key={i}>{t}</p>)}
    </div>
  );
}

async function persistTranscript(sessionId: string, text: string) {
  await fetch('/api/transcripts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessionId, text, ts: Date.now() }),
  });
}
```

## Cloudflare Worker — Persist to D1 with KV Rate-Limit

```typescript
// workers/transcripts.ts
import { Env } from './bindings';

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { sessionId, text, ts } = await req.json<{
      sessionId: string; text: string; ts: number;
    }>();

    // Rate-limit: max 120 inserts/min per session
    const rlKey = `rl:transcript:${sessionId}`;
    const count = parseInt((await env.KV.get(rlKey)) ?? '0', 10);
    if (count >= 120) return new Response('Rate limited', { status: 429 });
    await env.KV.put(rlKey, String(count + 1), { expirationTtl: 60 });

    await env.DB.prepare(
      'INSERT INTO transcripts (session_id, text, created_at) VALUES (?, ?, ?)'
    ).bind(sessionId, text, ts).run();

    return new Response(null, { status: 204 });
  },
};
```

## D1 Schema

```sql
-- migrations/0001_transcripts.sql
CREATE TABLE IF NOT EXISTS transcripts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT    NOT NULL,
  text       TEXT    NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_transcripts_session ON transcripts (session_id, created_at);
```

## Speech Synthesis with Edge-Fetched SSML

```typescript
// lib/speak.ts
export async function speakFromWorker(sessionId: string) {
  const resp = await fetch(`/api/tts-script?session=${sessionId}`);
  const { ssml } = await resp.json<{ ssml: string }>();

  const utterance = new SpeechSynthesisUtterance();
  utterance.lang = 'en-US';
  // SpeechSynthesis does not accept SSML directly in browsers;
  // strip tags and use text-only for cross-browser safety.
  utterance.text = ssml.replace(/<[^>]+>/g, '');
  speechSynthesis.speak(utterance);
}
```

## Workers AI Post-Processing (Optional)

```typescript
// workers/ai-summarize.ts  — summarize stored transcripts on demand
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const sessionId = new URL(req.url).searchParams.get('session') ?? '';
    const rows = await env.DB.prepare(
      'SELECT text FROM transcripts WHERE session_id = ? ORDER BY created_at'
    ).bind(sessionId).all<{ text: string }>();

    const combined = rows.results.map((r) => r.text).join(' ');
    const summary = await env.AI.run('@cf/facebook/bart-large-cnn', {
      input_text: combined,
      max_length: 130,
    });

    return Response.json(summary);
  },
};
```

## Anti-patterns

- **Sending audio blobs to Workers** — the browser already handles encoding and cloud transcription; shipping PCM/WAV to a Worker wastes bandwidth and quota.
- **Calling `rec.start()` inside `useEffect`** without an abort ref leaks a recognition session across hot-reloads.
- **Ignoring `rec.continuous = false`** for one-shot commands — use `false` there; `true` only for dictation.
- **Skipping the vendor prefix check** — `window.SpeechRecognition` is `undefined` in Safari until the feature ships unflagged.

## Gotchas

- `SpeechRecognition` requires a **secure context** (`https://` or `localhost`).
- Chrome's implementation routes audio to Google's servers; inform users in privacy policy.
- `onerror` fires with `'no-speech'` after ~7 s of silence in continuous mode — restart the recognizer to recover.
- `SpeechSynthesis.speak()` is blocked until a **user gesture** in all major browsers; call from a click handler.
- D1's write throughput is capped — batch transcript inserts with a short client-side debounce (250 ms) to avoid 429s.

## Verification

```bash
# Smoke-test the Worker endpoint locally
wrangler dev --local
curl -X POST http://localhost:8787/api/transcripts \
  -H 'Content-Type: application/json' \
  -d '{"sessionId":"test-1","text":"hello world","ts":1700000000000}'
# Expect: 204 No Content

# Query D1
wrangler d1 execute <DB_NAME> --command "SELECT * FROM transcripts LIMIT 5;"
```

## Related

- `indexeddb-offline-sync-cloudflare-d1-workers.md`
- `workers-analytics-engine-frontend-telemetry.md`
- `cloudflare-workers-ai-edge-inference-ui.md`
- `browser-permissions-api.md`

## Sources

- MDN Web Speech API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API
- Cloudflare D1 docs: https://developers.cloudflare.com/d1/
- Cloudflare Workers AI: https://developers.cloudflare.com/workers-ai/
- Cloudflare KV: https://developers.cloudflare.com/kv/
