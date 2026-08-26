# Web Audio API Workers CDN Audio Delivery

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You are building a music player, podcast app, or game sound engine that serves audio from Cloudflare R2 via Workers and needs low-latency, gapless, or procedurally processed playback in the browser. The `<audio>` element does not give you sample-level control, and basic `fetch + AudioBuffer` does not scale beyond small files.

## Context

The Web Audio API's `AudioContext` graph — source nodes, gain, analyser, effects, and the destination — runs in a dedicated audio worklet thread and is not blocked by the main thread. Cloudflare Workers serve audio from R2 with byte-range support, enabling browser-side streaming decode. Range requests allow seeking without re-downloading the file. Workers can also inject real-time metadata (BPM, key, waveform data) as custom response headers so the frontend can render a waveform before decoding.

---

## 1. Workers: R2 Audio Endpoint with Range Support

```typescript
// worker/audio.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const key = url.pathname.replace('/audio/', '');
    if (!key.match(/^[\w\-./]+\.(mp3|ogg|flac|wav|m4a)$/)) {
      return new Response('Not found', { status: 404 });
    }

    const rangeHeader = request.headers.get('Range');
    const object = await env.AUDIO_BUCKET.get(key, {
      range: rangeHeader ? parseRange(rangeHeader) : undefined,
    });

    if (!object) return new Response('Not found', { status: 404 });

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('Accept-Ranges', 'bytes');
    headers.set('Cache-Control', 'public, max-age=31536000, immutable');
    headers.set('Access-Control-Allow-Origin', '*');

    // Inject waveform peaks stored as custom metadata
    const peaks = object.customMetadata?.waveform_peaks;
    if (peaks) headers.set('X-Waveform-Peaks', peaks);

    const status = rangeHeader ? 206 : 200;
    if (rangeHeader && object.range) {
      const { offset = 0, length = object.size } = object.range as R2Range & { offset?: number; length?: number };
      headers.set('Content-Range', `bytes ${offset}-${offset + length - 1}/${object.size}`);
      headers.set('Content-Length', String(length));
    }

    return new Response(object.body, { status, headers });
  },
} satisfies ExportedHandler<Env>;

interface Env { AUDIO_BUCKET: R2Bucket; }

function parseRange(header: string): R2Range {
  const match = header.match(/^bytes=(\d+)-(\d*)$/);
  if (!match) return {};
  const offset = parseInt(match[1], 10);
  const end = match[2] ? parseInt(match[2], 10) : undefined;
  return end !== undefined
    ? { offset, length: end - offset + 1 }
    : { offset };
}
```

---

## 2. AudioContext Bootstrap and Unlock

```typescript
// lib/audio-context.ts
let _ctx: AudioContext | null = null;

/** Returns the shared AudioContext; creates it on first user gesture. */
export function getAudioContext(): AudioContext {
  if (!_ctx || _ctx.state === 'closed') {
    _ctx = new AudioContext({ latencyHint: 'playback', sampleRate: 44100 });
  }
  return _ctx;
}

/** Call inside a click/keydown handler to unlock autoplay on iOS and Chrome. */
export async function unlockAudioContext(): Promise<void> {
  const ctx = getAudioContext();
  if (ctx.state === 'suspended') await ctx.resume();
}
```

---

## 3. Streaming Decode via MediaSource Extensions (Large Files)

```typescript
// lib/mse-player.ts
export class MSEPlayer {
  private ms: MediaSource;
  private sb: SourceBuffer | null = null;
  private queue: ArrayBuffer[] = [];
  private appending = false;

  constructor(private readonly audioEl: HTMLAudioElement) {
    this.ms = new MediaSource();
    audioEl.src = URL.createObjectURL(this.ms);
    this.ms.addEventListener('sourceopen', () => this._onOpen());
  }

  private _onOpen(): void {
    // Use 'audio/mpeg' for MP3; adjust MIME for other codecs
    this.sb = this.ms.addSourceBuffer('audio/mpeg');
    this.sb.addEventListener('updateend', () => this._drain());
  }

  async load(url: string): Promise<void> {
    const res = await fetch(url, { headers: { 'Range': 'bytes=0-' } });
    if (!res.body) throw new Error('No body');
    const reader = res.body.getReader();

    while (true) {
      const { done, value } = await reader.read();
      if (done) { this.ms.endOfStream(); break; }
      this.queue.push(value.buffer);
      this._drain();
    }
  }

  private _drain(): void {
    if (!this.sb || this.sb.updating || this.queue.length === 0) return;
    this.appending = true;
    this.sb.appendBuffer(this.queue.shift()!);
  }
}
```

---

## 4. AudioBuffer Decode for Short Clips (SFX / One-shots)

```typescript
// lib/sfx-pool.ts
/** Pre-decode short audio files into AudioBuffers for zero-latency playback. */
export class SFXPool {
  private cache = new Map<string, AudioBuffer>();

  async preload(ctx: AudioContext, urls: string[]): Promise<void> {
    await Promise.all(
      urls.map(async (url) => {
        const res = await fetch(url);
        const raw = await res.arrayBuffer();
        const buf = await ctx.decodeAudioData(raw);
        this.cache.set(url, buf);
      })
    );
  }

  play(ctx: AudioContext, url: string, options: { gain?: number; loop?: boolean } = {}): AudioBufferSourceNode {
    const buf = this.cache.get(url);
    if (!buf) throw new Error(`SFX not loaded: ${url}`);

    const source = ctx.createBufferSource();
    source.buffer = buf;
    source.loop = options.loop ?? false;

    const gainNode = ctx.createGain();
    gainNode.gain.value = options.gain ?? 1;

    source.connect(gainNode).connect(ctx.destination);
    source.start();
    return source;
  }
}
```

---

## 5. Analyser Node for Waveform / VU Meter

```typescript
// lib/analyser.ts
export class AudioAnalyser {
  private analyser: AnalyserNode;
  private dataArray: Float32Array;
  private rafId = 0;

  constructor(ctx: AudioContext, sourceNode: AudioNode) {
    this.analyser = ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.dataArray = new Float32Array(this.analyser.frequencyBinCount);
    sourceNode.connect(this.analyser);
    this.analyser.connect(ctx.destination);
  }

  /** Call with a canvas 2D context to render a live waveform. */
  startDraw(canvas: HTMLCanvasElement): void {
    const ctx2d = canvas.getContext('2d')!;
    const draw = () => {
      this.rafId = requestAnimationFrame(draw);
      this.analyser.getFloatTimeDomainData(this.dataArray);

      ctx2d.clearRect(0, 0, canvas.width, canvas.height);
      ctx2d.beginPath();
      const sliceWidth = canvas.width / this.dataArray.length;
      let x = 0;
      for (const v of this.dataArray) {
        const y = ((v + 1) / 2) * canvas.height;
        x === 0 ? ctx2d.moveTo(x, y) : ctx2d.lineTo(x, y);
        x += sliceWidth;
      }
      ctx2d.strokeStyle = getComputedStyle(canvas).getPropertyValue('--color-accent') || '#6366f1';
      ctx2d.lineWidth = 1.5;
      ctx2d.stroke();
    };
    draw();
  }

  stop(): void { cancelAnimationFrame(this.rafId); }
}
```

---

## 6. Waveform Peak Generation in Workers (Upload-time)

```typescript
// worker/ingest.ts  (called at upload time, not on every request)
import { decodeAudio } from 'some-wasm-decoder'; // e.g. minimp3-wasm compiled to Workers

async function generatePeaks(buffer: ArrayBuffer, numPeaks = 200): Promise<number[]> {
  const samples = await decodeAudio(buffer); // Float32Array of PCM
  const blockSize = Math.floor(samples.length / numPeaks);
  const peaks: number[] = [];
  for (let i = 0; i < numPeaks; i++) {
    let max = 0;
    for (let j = 0; j < blockSize; j++) {
      max = Math.max(max, Math.abs(samples[i * blockSize + j]));
    }
    peaks.push(Math.round(max * 1000) / 1000);
  }
  return peaks;
}

// Store peaks in R2 custom metadata so the audio endpoint can serve them:
// await bucket.put(key, body, { customMetadata: { waveform_peaks: JSON.stringify(peaks) } });
```

---

## Anti-patterns

- **Creating a new `AudioContext` per play call** — browsers cap open contexts (~6 on Chrome); always share one context via a singleton.
- **Using `response.arrayBuffer()` for files over ~10 MB** — holds the entire compressed + decompressed audio in memory simultaneously; use MSE or `createMediaElementSource` for large files.
- **Starting playback before a user gesture** — `AudioContext` starts suspended on all major browsers; never call `start()` without first calling `ctx.resume()` inside a click/keydown handler.
- **Connecting the same source node twice** — `AudioBufferSourceNode` is one-shot; create a new node for each play invocation.
- **Forgetting `crossOrigin = 'anonymous'` on `<audio>` when using `createMediaElementSource`** — CORS errors block the audio graph even if the `<audio>` element plays fine on its own.

## Gotchas

- Cloudflare R2 `get` with a `Range` option returns an `R2ObjectBody` whose `.range` property only reflects the requested range when a `Content-Range` header was in the response; always compute the range from your own request object.
- iOS Safari requires the `AudioContext` to be created inside a `touchend` handler specifically — `click` works on desktop but not reliably on older iOS.
- `MediaSource` does not support all MIME types on all browsers; MP3 (`audio/mpeg`) is widest; Opus in WebM is best for Web Audio quality; always check `MediaSource.isTypeSupported()` before calling `addSourceBuffer`.
- Workers CPU limits mean on-the-fly audio transcoding is impractical; transcode at upload time and store multiple formats in R2.

## Verification

```bash
# Check byte-range support from the Worker:
curl -I -H "Range: bytes=0-1023" https://your-worker.workers.dev/audio/track.mp3
# Expect: HTTP/1.1 206 Partial Content
# Expect: Content-Range: bytes 0-1023/<total>
# Expect: Accept-Ranges: bytes

# Check waveform peaks metadata is present:
curl -sI https://your-worker.workers.dev/audio/track.mp3 | grep x-waveform
```

## Related

- `cloudflare-r2-presigned-upload-frontend.md`
- `web-midi-api-workers-audio-pipeline.md`
- `wasm-cloudflare-workers-image-transform.md`
- `background-fetch-api-r2-progressive-download.md`
- `webcodecs-api-cloudflare-workers-media-processing.md`

## Sources

- https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developer.mozilla.org/en-US/docs/Web/API/Media_Source_Extensions_API
- https://www.w3.org/TR/webaudio/
