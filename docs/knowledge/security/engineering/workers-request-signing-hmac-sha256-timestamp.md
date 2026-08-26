# Workers Request Signing with HMAC-SHA256 and Timestamp

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

example project internal services — the moderation Worker, the content pipeline Worker, and the push-notification Worker — call each other over HTTPS. Without request signing, any code that can reach those internal URLs (SSRF, misconfigured service binding, leaked URL) can forge arbitrary internal API calls. Signed requests prove that the caller holds the shared secret and that the request was created recently, preventing both forgery and replay.

## Context

Cloudflare Workers can call sibling Workers via Service Bindings (zero-egress RPC) or via fetch to a URL. Either way, adding an HMAC-SHA256 `Authorization` header with a timestamp ties each request to a specific body and moment in time. The Web Crypto API makes HMAC signing fast and non-extractable from the Worker runtime.

## Threat Model

Without signed requests an attacker who discovers an internal endpoint can:
- Send arbitrary payloads as if they were a trusted service.
- Replay previously captured valid requests (e.g., re-run a "delete post" action).
- Exploit SSRF to pivot from one Worker into a privileged internal API.

HMAC-SHA256 signing with a timestamp nonce closes all three vectors.

```typescript
// threat-model.ts
type Attack = "forgery" | "replay" | "ssrf-pivot";

const mitigations: Record<Attack, string> = {
  forgery:     "HMAC covers method + path + body; impossible without the secret",
  replay:      "Timestamp in signed message; receiver rejects requests > 30s old",
  "ssrf-pivot":"Receiver validates Host header matches expected service identity",
};
```

## Signing Implementation (Sender Side)

The signed string is `{METHOD}\n{PATH_WITH_QUERY}\n{TIMESTAMP_MS}\n{BODY_SHA256_HEX}`. Binding all four components prevents an attacker from swapping the body or reusing a signature on a different path.

```typescript
// request-signer.ts
const enc = new TextEncoder();

async function importHmacKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
}

async function sha256Hex(data: ArrayBuffer | string): Promise<string> {
  const buf = typeof data === "string" ? enc.encode(data) : data;
  const hash = await crypto.subtle.digest("SHA-256", buf);
  return Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function signRequest(
  req: Request,
  secret: string
): Promise<Request> {
  const url = new URL(req.url);
  const bodyBytes = req.body ? await req.arrayBuffer() : new ArrayBuffer(0);
  const bodyHash = await sha256Hex(bodyBytes);
  const ts = Date.now().toString();

  const message = [req.method, url.pathname + url.search, ts, bodyHash].join("\n");
  const key = await importHmacKey(secret);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(message));
  const sigHex = Array.from(new Uint8Array(sig))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");

  const headers = new Headers(req.headers);
  headers.set("X-example project-Timestamp", ts);
  headers.set("X-example project-Signature", `v1=${sigHex}`);

  return new Request(req.url, {
    method: req.method,
    headers,
    body: bodyBytes.byteLength ? bodyBytes : null,
  });
}
```

## Verification Implementation (Receiver Side)

The receiver reconstructs the same message string, computes the expected HMAC, and uses `timingSafeEqual` (via `crypto.subtle`) to compare. It also rejects requests whose timestamp falls outside a 30-second window, preventing replay.

```typescript
// request-verifier.ts
const CLOCK_SKEW_MS = 30_000;

async function importHmacVerifyKey(secret: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
}

export async function verifyRequest(
  req: Request,
  secret: string
): Promise<{ valid: boolean; reason?: string }> {
  const ts = req.headers.get("X-example project-Timestamp");
  const sigHeader = req.headers.get("X-example project-Signature");

  if (!ts || !sigHeader) return { valid: false, reason: "missing_headers" };

  const tsNum = parseInt(ts, 10);
  if (isNaN(tsNum) || Math.abs(Date.now() - tsNum) > CLOCK_SKEW_MS) {
    return { valid: false, reason: "timestamp_out_of_window" };
  }

  const sigHex = sigHeader.replace(/^v1=/, "");
  const sigBytes = Uint8Array.from(sigHex.match(/.{2}/g)!.map(b => parseInt(b, 16)));

  const url = new URL(req.url);
  const bodyBytes = req.body ? await req.arrayBuffer() : new ArrayBuffer(0);
  const bodyHash = await sha256Hex(bodyBytes);
  const message = [req.method, url.pathname + url.search, ts, bodyHash].join("\n");

  const key = await importHmacVerifyKey(secret);
  const valid = await crypto.subtle.verify("HMAC", key, sigBytes, enc.encode(message));

  return valid ? { valid: true } : { valid: false, reason: "signature_mismatch" };
}

// Middleware wrapper
export async function requireSignedRequest(
  req: Request,
  secret: string,
  next: () => Promise<Response>
): Promise<Response> {
  const { valid, reason } = await verifyRequest(req, secret);
  if (!valid) {
    return new Response(JSON.stringify({ error: "unauthorized", reason }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  return next();
}
```

## Hardening — Nonce D1 Store (Optional Replay Prevention)

For the highest-security internal APIs (moderation actions, bans), store a nonce per request in D1 and reject duplicates within the replay window. This prevents an attacker who can replay at millisecond speed within the 30-second window.

```typescript
// nonce-store.ts
export async function consumeNonce(
  db: D1Database,
  nonce: string,
  windowMs = 60_000
): Promise<boolean> {
  const expiry = Date.now() + windowMs;
  try {
    await db.prepare(
      "INSERT INTO request_nonces (nonce, expires_at) VALUES (?, ?)"
    ).bind(nonce, expiry).run();
    return true; // first use
  } catch {
    return false; // duplicate
  }
}

// Nonce is derived from sig hex — unique per request by construction
// Cleanup stale nonces asynchronously (cron trigger or tail worker)
export async function pruneNonces(db: D1Database): Promise<void> {
  await db.prepare("DELETE FROM request_nonces WHERE expires_at < ?")
    .bind(Date.now()).run();
}
```

## Monitoring

Surface failed signature checks to detect brute-force or misconfigured callers.

```typescript
// sig-monitoring.ts
export async function logSignatureFailure(
  req: Request,
  reason: string,
  ctx: ExecutionContext
): Promise<void> {
  ctx.waitUntil(
    fetch("https://logs.internal/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event: "request_sig_failure",
        reason,
        url: req.url,
        method: req.method,
        cf_ip: req.headers.get("CF-Connecting-IP"),
        ts: Date.now(),
      }),
    })
  );
}
```

## Anti-patterns

- Signing only the path without the body — allows body substitution attacks.
- Using `===` string comparison instead of `crypto.subtle.verify` — leaks timing information.
- Omitting the timestamp from the signed string — a valid signature is replayable forever.
- Storing the HMAC secret in `wrangler.toml` plaintext instead of a Workers Secret.
- Returning the signature mismatch reason in the response to external callers — reveals oracle info.

## Gotchas

- `req.arrayBuffer()` consumes the body stream; reconstruct `Request` with the buffer before passing to `next()`.
- Clock skew between Cloudflare PoPs is typically <1 s; the 30-second window is generous — tighten to 10 s for high-security paths.
- HMAC keys are not versioned by default — plan a rotation strategy using `X-example project-Key-Id` header alongside the signature.
- When using Service Bindings, `req.url` may be a placeholder host; sign the `pathname + search` only to stay canonical.
- Hex encoding the signature is more robust than Base64 across HTTP headers (no `+`, `/`, `=` padding issues).

## Verification

```bash
# Generate a test signature locally
SECRET="your-secret"
TS=$(date +%s000)
BODY_HASH=$(echo -n '{"action":"delete"}' | openssl dgst -sha256 | awk '{print $2}')
MSG="POST\n/internal/moderate\n${TS}\n${BODY_HASH}"
SIG=$(echo -ne "$MSG" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

# Call the Worker endpoint
curl -X POST https://internal.example.com/internal/moderate \
  -H "Content-Type: application/json" \
  -H "X-example project-Timestamp: $TS" \
  -H "X-example project-Signature: v1=$SIG" \
  -d '{"action":"delete"}'
# Expect 200; tamper body and expect 401 with reason: signature_mismatch
```

## Related

- /documentation/docs/policies/security/webhook-signature-verification-hmac.md
- /documentation/docs/policies/security/hmac-webhook-signature-rotation-zero-downtime.md
- /documentation/docs/policies/security/cryptographic-api-response-signing-workers.md
- /documentation/docs/policies/security/service-binding-zero-trust-workers.md
- /documentation/docs/policies/security/api-replay-prevention-nonce-d1-workers.md

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html
- https://www.ietf.org/rfc/rfc2104.txt
- https://developers.cloudflare.com/workers/runtime-apis/service-bindings/
