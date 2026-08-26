# Workers Multipart Form Parsing Security

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers endpoint accepts `multipart/form-data` submissions (file uploads, rich form
posts). Attackers submit crafted requests with boundary injection in field values, filenames
containing path traversal sequences, oversized field values meant to exhaust CPU/memory, or
unexpected MIME types to trigger downstream processing vulnerabilities.

## Context

The Workers runtime exposes `request.formData()` which wraps the browser-compatible
`FormData` API. The parser is spec-compliant but makes no security decisions: it accepts
any field name, any filename, and any amount of data the runtime allows. Security controls
must be layered on top before the parsed data is used or stored.

---

## Content-Type Validation

Reject requests that claim multipart but supply a malformed boundary, and reject
non-multipart requests to multipart-only endpoints early.

```typescript
function extractBoundary(contentType: string | null): string | null {
  if (!contentType) return null;
  const match = contentType.match(/^multipart\/form-data;\s*boundary=("?)([^"]+)\1$/i);
  if (!match) return null;
  const boundary = match[2];
  // RFC 2046: boundary is 1–70 chars, must not end in whitespace.
  if (boundary.length < 1 || boundary.length > 70) return null;
  if (/\s$/.test(boundary)) return null;
  return boundary;
}

export default {
  async fetch(request: Request): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const boundary = extractBoundary(request.headers.get("Content-Type"));
    if (!boundary) {
      return new Response("Expected multipart/form-data with valid boundary", {
        status: 415,
      });
    }

    return handleUpload(request);
  },
};
```

---

## Body Size Guard

Read the `Content-Length` header before calling `formData()`. If the declared size exceeds
your limit, reject immediately without consuming the body.

```typescript
const MAX_BODY_BYTES = 10 * 1024 * 1024; // 10 MiB

function guardBodySize(request: Request): Response | null {
  const cl = request.headers.get("Content-Length");
  if (cl !== null) {
    const declared = parseInt(cl, 10);
    if (isNaN(declared) || declared < 0 || declared > MAX_BODY_BYTES) {
      return new Response("Payload Too Large", { status: 413 });
    }
  }
  return null;
}
```

Note: `Content-Length` can be absent (chunked transfer) or spoofed. The guard above stops
honest large payloads early. For chunked bodies, the runtime enforces its own limit
(default 100 MiB); set a lower limit via a streaming wrapper if needed.

---

## Field Count and Name Validation

Unlimited form fields allow CPU exhaustion via field-name parsing. Enumerate fields after
parsing and enforce limits.

```typescript
const MAX_FIELDS   = 20;
const MAX_NAME_LEN = 64;
const ALLOWED_NAMES = new Set(["title", "description", "file", "thumbnail"]);

function validateFields(form: FormData): { error: string } | null {
  const entries = [...form.entries()];

  if (entries.length > MAX_FIELDS) {
    return { error: `Too many fields (max ${MAX_FIELDS})` };
  }

  for (const [name] of entries) {
    if (name.length > MAX_NAME_LEN) {
      return { error: `Field name too long: ${name.slice(0, 20)}…` };
    }
    if (!ALLOWED_NAMES.has(name)) {
      return { error: `Unknown field: ${name}` };
    }
  }

  return null;
}
```

---

## Filename Sanitisation

`File` objects in `FormData` carry a `name` property set by the browser (or attacker).
Never use this value to write to storage without sanitisation.

```typescript
const SAFE_FILENAME_RE = /^[\w\-. ]+$/; // alphanumeric, dash, dot, space, underscore
const MAX_FILENAME_LEN = 200;

function sanitiseFilename(raw: string): string {
  // Strip directory components.
  const base = raw.split(/[\\/]/).pop() ?? "upload";

  // Remove null bytes and control characters.
  const cleaned = base.replace(/[\x00-\x1f\x7f]/g, "");

  // Enforce allowlist of safe characters.
  const safe = cleaned.replace(/[^\w\-. ]/g, "_");

  // Truncate.
  const truncated = safe.slice(0, MAX_FILENAME_LEN);

  // Prevent Windows reserved names and leading dots (hidden files).
  const noDot    = truncated.replace(/^\.+/, "_");
  const noReserved = noDot.replace(
    /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)/i,
    "_$1$2",
  );

  return noReserved || "upload";
}
```

---

## File Type Validation (Magic Bytes)

Do not trust the `File.type` property — it comes from the browser's guess or attacker
input. Read the first bytes and compare against known magic numbers.

```typescript
const ALLOWED_MAGIC: Array<{ mime: string; bytes: Uint8Array }> = [
  { mime: "image/jpeg", bytes: new Uint8Array([0xff, 0xd8, 0xff]) },
  { mime: "image/png",  bytes: new Uint8Array([0x89, 0x50, 0x4e, 0x47]) },
  { mime: "image/webp", bytes: new Uint8Array([0x52, 0x49, 0x46, 0x46]) },
  { mime: "application/pdf", bytes: new Uint8Array([0x25, 0x50, 0x44, 0x46]) },
];

async function detectMime(file: File): Promise<string | null> {
  const slice = await file.slice(0, 8).arrayBuffer();
  const bytes = new Uint8Array(slice);

  for (const { mime, bytes: magic } of ALLOWED_MAGIC) {
    if (magic.every((b, i) => bytes[i] === b)) return mime;
  }
  return null;
}
```

---

## Full Handler

```typescript
async function handleUpload(request: Request): Promise<Response> {
  const sizeError = guardBodySize(request);
  if (sizeError) return sizeError;

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return new Response("Malformed multipart body", { status: 400 });
  }

  const fieldError = validateFields(form);
  if (fieldError) return new Response(fieldError.error, { status: 422 });

  const file = form.get("file");
  if (!(file instanceof File)) {
    return new Response("Missing file field", { status: 422 });
  }

  const detectedMime = await detectMime(file);
  if (!detectedMime) {
    return new Response("Unsupported or unrecognised file type", { status: 415 });
  }

  const safeName = sanitiseFilename(file.name);
  const key      = `uploads/${crypto.randomUUID()}/${safeName}`;

  // Hand off to R2, S3, or other storage — never write raw filename.
  return new Response(JSON.stringify({ key, mime: detectedMime }), {
    headers: { "Content-Type": "application/json" },
  });
}
```

---

## Anti-patterns

- **Using `file.name` directly as a storage key** — leads to path traversal and
  overwrite attacks.
- **Trusting `file.type`** — the browser fills this from the file extension; an attacker
  sets it arbitrarily. Always verify magic bytes.
- **Calling `formData()` without a body size guard** — a 2 GiB chunked upload fully
  buffers in the runtime before your code runs a single validation.
- **Accepting arbitrary field names** — attackers flood with thousands of random fields to
  amplify parser CPU cost (hash-flooding via field-name collisions in some implementations).
- **Reflecting the original filename in the response** — exposes internal path structures
  and enables stored XSS if the filename contains HTML.

## Gotchas

- `request.formData()` throws on malformed boundaries; always wrap in try/catch.
- The Workers runtime buffers the entire body when `formData()` is called — there is no
  streaming parser. For very large uploads, use a pre-signed R2 URL and upload directly
  from the client, bypassing the Worker entirely.
- `File.size` reflects the declared size from the multipart header, not the actual read
  bytes. Verify against actual `ArrayBuffer` length if precision is required.
- WebP validation via magic bytes requires checking bytes 8–11 (`WEBP`) in addition to
  `RIFF` at bytes 0–3; the simple check above only detects the container.

## Verification

```bash
# Malformed boundary → 415
curl -si -X POST https://api.example.com/upload \
  -H "Content-Type: multipart/form-data; boundary=" \
  -d "" | grep HTTP

# Path traversal filename — response key must not contain ../
curl -si -X POST https://api.example.com/upload \
  -F "file=@test.jpg;filename=../../etc/passwd" \
  | jq .key

# Oversized payload → 413
dd if=/dev/zero bs=1M count=20 | curl -si -X POST https://api.example.com/upload \
  -H "Content-Type: multipart/form-data; boundary=x" \
  --data-binary @- | grep HTTP
```

## Related

- `workers-input-size-limit-dos-prevention.md` — body size limits before parsing
- `file-upload-security-pipeline.md` — downstream malware scanning and storage hardening
- `r2-multipart-upload-abuse-prevention-workers.md` — preventing R2 multipart upload abuse
- `path-traversal-prevention.md` — general path traversal patterns

## Sources

- RFC 2046 — MIME Multipart: https://www.rfc-editor.org/rfc/rfc2046
- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- Cloudflare Workers FormData: https://developers.cloudflare.com/workers/runtime-apis/request/#the-body
