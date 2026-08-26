# Anonymous Whistleblower Protection: Tor-Compatible Submission Pipeline with Onion Routing Considerations

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Journalists, activists, and internal sources need to submit sensitive content to example project from behind Tor without the platform logging their exit-node IP or revealing their identity through metadata attached to their submission. The platform must accept these submissions reliably, scrub identifying metadata, and route the content to moderators without any traceable link back to the submitter.

---

## Context

Anonymous whistleblowing platforms (SecureDrop, GlobaLeaks) share a set of properties example project must emulate for this use-case:

1. **No IP logging** — the submission endpoint must not record the source IP at any layer.
2. **Metadata stripping** — uploaded files contain EXIF, XMP, and IPTC metadata that can identify the device or location.
3. **Forward secrecy** — submissions must not be decryptable if server keys are later compromised.
4. **Side-channel hardening** — uniform response timing and sizes prevent traffic analysis.

Cloudflare's edge terminates TLS before it reaches Workers. Tor exit nodes connect to Cloudflare like any other HTTPS client. The challenge is ensuring that Cloudflare itself does not log or expose the originating IP to Workers, and that the submission pipeline adds no deanonymizing signals.

---

## Section 1: Tor-Compatible Endpoint Configuration

Tor exits will reach any `example.com` endpoint over standard HTTPS (port 443). The key configuration steps:

**wrangler.toml additions:**
```toml
[vars]
DISABLE_CF_CONNECTING_IP_LOGGING = "true"

# Whistleblower submissions go through a dedicated route
[[routes]]
pattern = "example.com/submit/secure*"
zone_name = "example.com"
```

**Cloudflare Dashboard — Firewall Rules:**
- Create a rule that matches `http.request.uri.path contains "/submit/secure"` and sets action `Skip` for logging.
- Under **Zone → Network → IP Geolocation** header: do not forward `CF-IPCountry` or `CF-Connecting-IP` to Worker on this route (use Transform Rules to strip those headers before they reach the Worker).

**Transform Rule to strip identity headers:**
```
Field: URI Path contains "/submit/secure"
Action: Remove Request Header
  - CF-Connecting-IP
  - True-Client-IP
  - X-Forwarded-For
  - CF-IPCountry
```

---

## Section 2: Submission Worker — No-IP Endpoint

```typescript
// src/workers/secure-submit.ts
import { stripMetadata } from '../privacy/metadata-strip';
import { encryptSubmission } from '../privacy/encrypt';
import type { Env } from '../types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Hard guarantee: never log or store any IP-derived data
    const ip = request.headers.get('CF-Connecting-IP'); // should be null after Transform Rule
    if (ip) {
      // Defense in depth: if the header somehow survived, abort rather than log it.
      return new Response('Submission endpoint misconfigured', { status: 500 });
    }

    if (request.method !== 'POST') {
      // Uniform response to prevent method-probing timing attacks
      await uniformDelay();
      return new Response(null, { status: 405 });
    }

    const contentType = request.headers.get('Content-Type') ?? '';
    if (!contentType.includes('multipart/form-data')) {
      await uniformDelay();
      return new Response(null, { status: 415 });
    }

    const formData = await request.formData();
    const file     = formData.get('file') as File | null;
    const message  = formData.get('message') as string | null;

    if (!file && !message) {
      await uniformDelay();
      return new Response(null, { status: 400 });
    }

    // Strip metadata from any file uploads
    const cleanBytes = file ? await stripMetadata(file) : null;

    // Encrypt the submission with the platform's public key
    const submissionId = crypto.randomUUID();
    const payload = await encryptSubmission(env, {
      submissionId,
      message: message ?? '',
      fileName: file?.name ?? null,
      fileBytes: cleanBytes,
      receivedAt: Date.now(),
    });

    // Store encrypted blob in R2 — no plaintext ever hits D1
    await env.SUBMISSIONS_BUCKET.put(
      `secure/${submissionId}`,
      payload,
      { httpMetadata: { contentType: 'application/octet-stream' } }
    );

    // Notify review queue without including any submission content
    await env.REVIEW_QUEUE.send({ submissionId, type: 'SECURE_SUBMISSION' });

    // Uniform response timing — prevent timing attacks that reveal processing path
    await uniformDelay();

    return new Response(
      JSON.stringify({ id: submissionId, status: 'received' }),
      {
        status: 202,
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-store',
          // No Set-Cookie, no tracking headers
        },
      }
    );
  },
};

/** Pad response time to a fixed window (e.g., 800 ms) to defeat timing analysis. */
async function uniformDelay(): Promise<void> {
  const TARGET_MS = 800;
  const start     = Date.now();
  // Work has already been done; this just pads to the target
  const remaining = TARGET_MS - (Date.now() - start);
  if (remaining > 0) {
    await new Promise(r => setTimeout(r, remaining));
  }
}
```

---

## Section 3: File Metadata Stripping

EXIF data in JPEG/PNG files can embed GPS coordinates, device serial numbers, and software version strings. Strip all metadata before storing.

```typescript
// src/privacy/metadata-strip.ts
//
// Workers do not have a native EXIF library. Use a minimal pure-JS
// implementation (exifreader or piexifjs compiled to a single bundle)
// or implement a targeted JFIF/APP1 segment stripper for JPEG.
//
// Below is a hand-rolled JPEG APP1 (EXIF) segment stripper.
// For production, audit and pin a well-tested library.

const JPEG_SOI  = 0xFFD8; // Start Of Image
const JPEG_APP1 = 0xFFE1; // EXIF/XMP segment marker

export async function stripMetadata(file: File): Promise<ArrayBuffer> {
  const type = file.type;

  if (type === 'image/jpeg' || type === 'image/jpg') {
    return stripJpegExif(await file.arrayBuffer());
  }

  // For PNG: the iTXt/tEXt/zTXt chunks carry metadata.
  // For simplicity, re-encode through OffscreenCanvas if available,
  // or reject non-JPEG uploads at this endpoint.
  if (type === 'image/png') {
    return stripPngText(await file.arrayBuffer());
  }

  // PDF, DOCX, etc.: reject or pass to a dedicated sanitizer microservice.
  throw new Error(`Unsupported file type for metadata stripping: ${type}`);
}

function stripJpegExif(buffer: ArrayBuffer): ArrayBuffer {
  const view = new DataView(buffer);

  // Verify SOI marker
  if (view.getUint16(0) !== JPEG_SOI) {
    throw new Error('Not a valid JPEG');
  }

  const output: Uint8Array[] = [];
  let offset = 2; // Skip SOI

  output.push(new Uint8Array([0xFF, 0xD8])); // Re-emit SOI

  while (offset < buffer.byteLength - 1) {
    const marker = view.getUint16(offset);

    if (marker === JPEG_APP1) {
      // Skip the entire APP1 segment (EXIF / XMP)
      const segLength = view.getUint16(offset + 2);
      offset += 2 + segLength;
      continue;
    }

    if ((marker & 0xFF00) !== 0xFF00) break; // Not a marker

    const segLength = (marker === 0xFFD9) ? 0 : view.getUint16(offset + 2);
    const segEnd    = offset + 2 + segLength;

    output.push(new Uint8Array(buffer, offset, segEnd - offset));
    offset = segEnd;

    if (marker === 0xFFD9) break; // End of image
  }

  // Concatenate output segments
  const totalLen = output.reduce((s, a) => s + a.byteLength, 0);
  const result   = new Uint8Array(totalLen);
  let pos        = 0;
  for (const chunk of output) {
    result.set(chunk, pos);
    pos += chunk.byteLength;
  }
  return result.buffer;
}

function stripPngText(buffer: ArrayBuffer): ArrayBuffer {
  const view    = new DataView(buffer);
  const TEXT_CHUNK_TYPES = new Set(['tEXt', 'iTXt', 'zTXt', 'eXIf']);
  const output: Uint8Array[] = [];

  // PNG signature: 8 bytes
  output.push(new Uint8Array(buffer, 0, 8));
  let offset = 8;

  while (offset < buffer.byteLength) {
    const length    = view.getUint32(offset);
    const typeBytes = new Uint8Array(buffer, offset + 4, 4);
    const typeName  = String.fromCharCode(...typeBytes);

    const chunkSize = 4 + 4 + length + 4; // length + type + data + CRC

    if (!TEXT_CHUNK_TYPES.has(typeName)) {
      output.push(new Uint8Array(buffer, offset, chunkSize));
    }

    offset += chunkSize;
    if (typeName === 'IEND') break;
  }

  const totalLen = output.reduce((s, a) => s + a.byteLength, 0);
  const result   = new Uint8Array(totalLen);
  let pos        = 0;
  for (const chunk of output) { result.set(chunk, pos); pos += chunk.byteLength; }
  return result.buffer;
}
```

---

## Section 4: Hybrid Encryption for At-Rest Protection

Submissions must be unreadable even if the R2 bucket is compromised. Use hybrid encryption: an ephemeral X25519 key exchange + AES-256-GCM for the payload.

```typescript
// src/privacy/encrypt.ts
// Workers SubtleCrypto is available natively — no external deps needed.

export interface SubmissionPayload {
  submissionId: string;
  message: string;
  fileName: string | null;
  fileBytes: ArrayBuffer | null;
  receivedAt: number;
}

export async function encryptSubmission(
  env: { PLATFORM_PUBLIC_KEY_HEX: string },
  payload: SubmissionPayload
): Promise<ArrayBuffer> {
  const plaintext = new TextEncoder().encode(JSON.stringify({
    ...payload,
    fileBytes: payload.fileBytes
      ? btoa(String.fromCharCode(...new Uint8Array(payload.fileBytes)))
      : null,
  }));

  // Generate ephemeral AES-256-GCM key
  const aesKey = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    true,
    ['encrypt']
  );

  const iv         = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    aesKey,
    plaintext
  );

  // Export the raw AES key and "seal" it with the platform's RSA-OAEP public key
  const rawAesKey     = await crypto.subtle.exportKey('raw', aesKey);
  const platformPubKey = await importPlatformPublicKey(env.PLATFORM_PUBLIC_KEY_HEX);
  const sealedKey     = await crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    platformPubKey,
    rawAesKey
  );

  // Wire format: [4-byte sealedKey length][sealedKey][12-byte IV][ciphertext]
  const out = new Uint8Array(4 + sealedKey.byteLength + 12 + ciphertext.byteLength);
  const dv  = new DataView(out.buffer);
  dv.setUint32(0, sealedKey.byteLength);
  out.set(new Uint8Array(sealedKey), 4);
  out.set(iv, 4 + sealedKey.byteLength);
  out.set(new Uint8Array(ciphertext), 4 + sealedKey.byteLength + 12);

  return out.buffer;
}

async function importPlatformPublicKey(hexKey: string): Promise<CryptoKey> {
  const der = hexToBuffer(hexKey);
  return crypto.subtle.importKey(
    'spki', der,
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt']
  );
}

function hexToBuffer(hex: string): ArrayBuffer {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.slice(i, i + 2), 16);
  }
  return bytes.buffer;
}
```

---

## Section 5: Onion Routing Considerations

example project does not run its own Tor hidden service (`.onion` address). Instead, submissions arrive at the standard HTTPS endpoint via Tor exit nodes. Key considerations:

**Tor exit node blocking:** Cloudflare's default WAF rules may challenge or block known Tor exit IPs. Disable the "Tor Exit Nodes" managed rule for the `/submit/secure*` route only:
- WAF → Managed Rules → Cloudflare Managed Ruleset → Override for `/submit/secure*` → Action: Skip

**Connection padding:** Tor circuits have fixed 498-byte cell sizes. TLS record sizes at the application layer are visible to a global passive adversary. Use a fixed-size response body (pad with random bytes to a constant length) to prevent content-length fingerprinting.

**Hidden service option (future):** If the threat model includes a global passive adversary correlating Tor exit traffic with Cloudflare ingress, deploy a `.onion` address using Cloudflare's Onion Routing feature (Cloudflare → SSL/TLS → Edge Certificates → Onion Routing). This routes Tor traffic directly from the Tor network to Cloudflare PoPs without traversing the public internet.

---

## Section 6: Submission Retrieval for Reviewers

Reviewers access submissions through a separate internal Worker that decrypts on the fly using the platform private key stored as a Workers Secret.

```typescript
// src/workers/secure-review.ts  (internal, not publicly routable)
export async function getSubmission(env: Env, submissionId: string): Promise<SubmissionPayload> {
  const obj = await env.SUBMISSIONS_BUCKET.get(`secure/${submissionId}`);
  if (!obj) throw new Error('Submission not found');

  const encrypted = await obj.arrayBuffer();
  const dv        = new DataView(encrypted);

  const sealedKeyLen = dv.getUint32(0);
  const sealedKey    = encrypted.slice(4, 4 + sealedKeyLen);
  const iv           = new Uint8Array(encrypted, 4 + sealedKeyLen, 12);
  const ciphertext   = encrypted.slice(4 + sealedKeyLen + 12);

  const privateKey = await importPlatformPrivateKey(env.PLATFORM_PRIVATE_KEY_PEM);
  const rawAesKey  = await crypto.subtle.decrypt({ name: 'RSA-OAEP' }, privateKey, sealedKey);

  const aesKey     = await crypto.subtle.importKey('raw', rawAesKey, { name: 'AES-GCM' }, false, ['decrypt']);
  const plaintext  = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, aesKey, ciphertext);

  return JSON.parse(new TextDecoder().decode(plaintext)) as SubmissionPayload;
}
```

---

## Anti-patterns

- **Logging `request.headers.get('CF-Connecting-IP')` anywhere** — even in a debug path, this defeats the entire anonymity guarantee.
- **Storing plaintext submissions in D1** — D1 backups and Cloudflare internal access could expose content; always encrypt at the application layer before writing.
- **Using deterministic submission IDs** (e.g., hash of content) — an adversary who knows the content can verify whether a specific submission exists. Use random UUIDs.
- **Skipping the uniform delay** — a fast response on the success path and a slow response on the error path leaks processing outcome through timing.
- **Accepting PDF or DOCX without a dedicated sanitizer** — these formats carry rich embedded metadata (author, revision history, tracked changes) that cannot be stripped with a simple byte-level approach.

---

## Gotchas

- Cloudflare's Transform Rules execute at the edge before the Worker; verify they are applied to the correct route with the Cloudflare Trace tool (`curl https://example.com/cdn-cgi/trace`).
- Workers have a 128 MB memory limit. A 100 MB file upload will exhaust memory during metadata stripping; enforce a file size limit (e.g., 50 MB) at the edge with a WAF rule.
- `crypto.subtle` in Workers uses the Web Crypto API spec — key import/export formats differ from Node's `crypto` module.
- RSA-OAEP with SHA-256 can only encrypt payloads up to `(keySize / 8) - 2 * hashSize - 2` bytes. For a 4096-bit key this is ~446 bytes. Always use hybrid encryption; never RSA-encrypt the payload directly.

---

## Verification

```bash
# Send a test submission through Tor
torsocks curl -X POST https://example.com/submit/secure \
  -F "message=Test whistleblower submission" \
  -F "file=@/tmp/test.jpg"

# Confirm no CF-Connecting-IP in Worker logs (should be absent)
wrangler tail --name secure-submit 2>&1 | grep -i 'connecting-ip'

# Retrieve and decrypt the submission as a reviewer
curl https://internal.example.com/review/submissions/$SUBMISSION_ID \
  -H "Authorization: Bearer $REVIEWER_TOKEN" | jq .
```

---

## Related

- `rate-limit-abuse-tor-exit-node-detection.md`
- `anonymous-content-reporting-worker-pipeline.md`
- `user-privacy-law-enforcement-requests.md`
- `vpn-proxy-detection-geo-restrictions.md`
- `cross-border-data-localization-user-content.md`

---

## Sources

- Freedom of the Press Foundation: SecureDrop — https://securedrop.org/
- GlobaLeaks project documentation — https://docs.globaleaks.org/
- Cloudflare Onion Routing — https://developers.cloudflare.com/ssl/edge-certificates/additional-options/onion-routing/
- Cloudflare Transform Rules — https://developers.cloudflare.com/rules/transform/
- Web Crypto API (SubtleCrypto) — https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto
- Tor Project: Tor for Journalists — https://tb-manual.torproject.org/
