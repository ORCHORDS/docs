# WebCodecs API — Client-Side Media Processing with Cloudflare Workers Upload

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You want to encode user-recorded or user-selected video to a specific codec (H.264,
VP9, AV1) entirely in the browser — trimming, transcoding, thumbnail extraction — and
then upload the result to Cloudflare R2 without routing the raw video through a server.
The WebCodecs API gives access to hardware-accelerated encode/decode pipelines without
a WASM codec library.

## Context

The **WebCodecs API** provides low-level access to the browser's media codecs via
`VideoEncoder`, `VideoDecoder`, `AudioEncoder`, `AudioDecoder`, `VideoFrame`,
`ImageDecoder`, and `EncodedVideoChunk`. It is available in Chrome/Edge 94+,
Safari 16.4+ (subset), and Firefox 130+ (subset, behind a flag until late 2025).

WebCodecs runs on the main thread or in a Dedicated Worker (recommended for heavy
processing to keep the UI responsive). Cloudflare Workers handle upload coordination
and presigned URL generation; actual encoding happens entirely client-side.

## Feature Detection

```typescript
// lib/webcodecs.ts

export const supportsWebCodecs =
  typeof window !== 'undefined' &&
  typeof VideoEncoder !== 'undefined' &&
  typeof VideoDecoder !== 'undefined';

export async function checkEncoderSupport(
  codec: string, // e.g. 'avc1.42001E' (H.264 Baseline)
): Promise<VideoEncoderSupport> {
  if (!supportsWebCodecs) {
    return { supported: false, config: { codec, width: 0, height: 0 } } as VideoEncoderSupport;
  }
  return VideoEncoder.isConfigSupported({ codec, width: 1280, height: 720 });
}
```

## Extracting Video Frames with VideoDecoder

```typescript
// lib/decode.ts

export interface DecodedFrameResult {
  frame: VideoFrame;
  timestamp: number; // microseconds
}

export async function decodeFirstNFrames(
  encodedData: ArrayBuffer,
  codec: string,
  maxFrames: number,
  onFrame: (result: DecodedFrameResult) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    let count = 0;

    const decoder = new VideoDecoder({
      output(frame) {
        if (count < maxFrames) {
          onFrame({ frame, timestamp: frame.timestamp });
          count++;
        } else {
          frame.close(); // Always close frames you do not consume
        }
        if (count >= maxFrames) {
          decoder.close();
          resolve();
        }
      },
      error(err) {
        reject(err);
      },
    });

    decoder.configure({ codec });

    // Treat the entire buffer as a single chunk for demuxing purposes.
    // In production, use mp4box.js or a similar demuxer to extract individual NAL units.
    decoder.decode(
      new EncodedVideoChunk({
        type: 'key',
        timestamp: 0,
        data: encodedData,
      }),
    );

    decoder.flush().then(resolve).catch(reject);
  });
}
```

For real-world demuxing use `mp4box.js` (MIT) to extract `EncodedVideoChunk` objects
per-sample before feeding them to `VideoDecoder`.

## Re-encoding with VideoEncoder

```typescript
// lib/encode.ts

export interface EncodeOptions {
  codec: string;        // e.g. 'avc1.42001E'
  width: number;
  height: number;
  bitrate: number;      // bps
  framerate: number;
}

export async function encodeFrames(
  frames: VideoFrame[],
  options: EncodeOptions,
): Promise<Uint8Array> {
  const chunks: EncodedVideoChunk[] = [];

  return new Promise<Uint8Array>((resolve, reject) => {
    const encoder = new VideoEncoder({
      output(chunk) {
        chunks.push(chunk);
      },
      error(err) {
        reject(err);
      },
    });

    encoder.configure({
      codec: options.codec,
      width: options.width,
      height: options.height,
      bitrate: options.bitrate,
      framerate: options.framerate,
      hardwareAcceleration: 'prefer-hardware',
    });

    for (let i = 0; i < frames.length; i++) {
      const frame = frames[i];
      const keyFrame = i % options.framerate === 0; // keyframe every second
      encoder.encode(frame, { keyFrame });
      frame.close();
    }

    encoder.flush().then(() => {
      encoder.close();

      // Concatenate all chunk data into one buffer
      const totalSize = chunks.reduce((acc, c) => acc + c.byteLength, 0);
      const output = new Uint8Array(totalSize);
      let offset = 0;
      for (const chunk of chunks) {
        const buf = new ArrayBuffer(chunk.byteLength);
        chunk.copyTo(buf);
        output.set(new Uint8Array(buf), offset);
        offset += chunk.byteLength;
      }
      resolve(output);
    }).catch(reject);
  });
}
```

## Extracting a Thumbnail from a Video Element

```typescript
// lib/thumbnail.ts

export async function extractThumbnail(
  videoEl: HTMLVideoElement,
  atSeconds = 1,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    videoEl.currentTime = atSeconds;
    videoEl.addEventListener('seeked', async () => {
      try {
        const frame = new VideoFrame(videoEl);
        const canvas = new OffscreenCanvas(frame.codedWidth, frame.codedHeight);
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(frame, 0, 0);
        frame.close();
        const blob = await canvas.convertToBlob({ type: 'image/webp', quality: 0.85 });
        resolve(blob);
      } catch (err) {
        reject(err);
      }
    }, { once: true });
  });
}
```

## Cloudflare Workers: Presigned R2 Upload Endpoint

The Worker issues a presigned URL so the client can PUT the encoded video directly to
R2 without the binary passing through the Worker:

```typescript
// workers/upload-sign.ts
import { AwsClient } from 'aws4fetch'; // MIT, works in Workers

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const { filename, contentType } = await req.json<{
      filename: string;
      contentType: string;
    }>();

    const key = `uploads/${crypto.randomUUID()}/${filename}`;
    const aws = new AwsClient({
      accessKeyId: env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
      region: 'auto',
      service: 's3',
    });

    const r2Url = `https://${env.R2_BUCKET_NAME}.${env.ACCOUNT_ID}.r2.cloudflarestorage.com/${key}`;
    const signed = await aws.sign(
      new Request(r2Url, { method: 'PUT', headers: { 'Content-Type': contentType } }),
      { aws: { signQuery: true } },
    );

    return Response.json({ uploadUrl: signed.url, key });
  },
} satisfies ExportedHandler<Env>;
```

Client upload after encoding:

```typescript
// lib/upload.ts
import { encodeFrames, EncodeOptions } from './encode';

export async function uploadEncodedVideo(
  frames: VideoFrame[],
  options: EncodeOptions,
  filename: string,
): Promise<{ key: string }> {
  const encoded = await encodeFrames(frames, options);

  // 1. Get presigned URL from Cloudflare Worker
  const { uploadUrl, key } = await fetch('/api/upload-sign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, contentType: 'video/mp4' }),
  }).then((r) => r.json<{ uploadUrl: string; key: string }>());

  // 2. PUT directly to R2
  const resp = await fetch(uploadUrl, {
    method: 'PUT',
    body: encoded,
    headers: { 'Content-Type': 'video/mp4' },
  });

  if (!resp.ok) throw new Error(`Upload failed: ${resp.status}`);
  return { key };
}
```

## Anti-patterns

- **Not closing `VideoFrame` objects.** Frames hold GPU memory. Call `frame.close()`
  immediately after use or you will exhaust the frame pool and receive
  `QuotaExceededError`.
- **Running VideoEncoder on the main thread for long videos.** Move encoding into a
  `Worker` (browser) and use `Transferable` `VideoFrame` objects.
- **Passing the whole MP4 file as a single `EncodedVideoChunk`.** Decoders expect
  per-sample chunks. Use a demuxer (`mp4box.js`, `mp4-muxer`, or `@webav/av-cliper`).
- **Using `VideoEncoder` without `isConfigSupported`.** Unsupported configs throw
  synchronously in `configure()`. Always check support first.

## Gotchas

- Safari 16.4+ supports `VideoDecoder` and `VideoEncoder` for H.264 only; AV1/VP9
  encode is not available on Apple silicon via WebCodecs.
- `hardwareAcceleration: 'prefer-hardware'` may be ignored; the browser chooses the
  actual path.
- `EncodedVideoChunk.copyTo()` is the only way to read chunk bytes — there is no
  `.getData()` getter.
- TypeScript: WebCodecs types ship in `lib.dom.d.ts` from TypeScript 5.3+. For earlier
  versions install `@types/dom-webcodecs`.
- The `VideoEncoder` `output` callback fires synchronously inside `flush().then()`
  resolution in some browser versions; do not assume output order matches input order.

## Verification

1. Open Chrome DevTools → Performance → record while encoding a 30-second clip. GPU
   acceleration shows as "GPU-accelerated encoding" in the encoder config response.
2. Check the R2 bucket in the Cloudflare dashboard for the uploaded file after
   `uploadEncodedVideo` completes.
3. Play the resulting video in a plain `<video>` tag — it must be playable to confirm
   the encoded bitstream is valid.
4. Close all `VideoFrame` objects in tests; run `performance.memory.usedJSHeapSize`
   before and after to confirm no leak.
5. Test on Safari 16.4 with `codec: 'avc1.42001E'`; confirm encode succeeds and the
   AV1 path falls back gracefully.

## Related

- `wasm-cloudflare-workers-image-transform.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `browser-web-workers.md`
- `file-upload-ux-chunked-resumable.md`
- `origin-private-file-system-opfs-cloudflare-pages.md`
- `video-autoplay-mobile-restrictions-hls.md`

## Sources

- https://developer.chrome.com/docs/web-platform/best-practices/webcodecs
- https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API
- https://w3c.github.io/webcodecs/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://github.com/nickvdyck/webtransport#webcodecs-integration
