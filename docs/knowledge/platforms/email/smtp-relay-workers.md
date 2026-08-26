# SMTP Relay Configuration for Cloudflare Workers

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Legacy applications, SaaS platforms, and developer tools that speak SMTP cannot directly call a REST API like Resend or SendGrid. They need an **SMTP relay endpoint**—a host and port they can connect to using standard SMTP commands (EHLO, AUTH, MAIL FROM, RCPT TO, DATA). Migrating these callers to a REST API would require code changes across many services.

Cloudflare Workers cannot open TCP listeners (they are HTTP-only), so a true SMTP server cannot run natively in a Worker. However, Workers *can* act as an **SMTP-to-REST bridge**: a thin relay server (running on a Cloudflare-adjacent compute layer or a lightweight VM) forwards SMTP traffic to a Worker over HTTPS, which then delivers via a modern ESP API. The SMTP relay terminates TLS, validates credentials, and proxies the message body.

This article covers two deployment patterns:
1. **External relay → Worker** — a minimal Node.js/Haraka relay terminates SMTP and calls a Worker.
2. **Cloudflare Tunnel + smtp2http** — a zero-trust tunnel exposes a local relay without a public IP.

---

## Context

Cloudflare Workers runs on the V8 isolate runtime. Key networking constraints:

| Capability | Supported |
|-----------|-----------|
| Outbound HTTP/HTTPS (`fetch`) | Yes |
| Outbound TCP (`connect`) | Yes — via `cloudflare:sockets` (Workers Socket API) |
| Inbound TCP listeners | **No** |
| SMTP server socket | **No** — must be handled externally |

The **Workers Socket API** (`import { connect } from "cloudflare:sockets"`) enables *outbound* SMTP (useful for direct delivery or relay forwarding), but inbound SMTP requires an external listener.

---

## Section 1: Architecture

**Pattern A — External relay + Worker webhook**

```
SMTP Client (port 587)
        │
        ▼
  smtp-relay.example.com:587
  (Node.js / Haraka / smtp2http)
        │  HTTP POST  /smtp/inbound
        ▼
  Cloudflare Worker
        │  REST API call
        ▼
  ESP (Resend / SendGrid / Postmark)
```

**Pattern B — Cloudflare Tunnel**

```
SMTP Client (port 587)
        │
        ▼
  localhost:587 (smtp2http)
        │
        ▼
  cloudflared tunnel → Worker
        │
        ▼
  ESP
```

---

## Section 2: Worker SMTP Bridge Endpoint

The Worker receives a normalized email payload from the relay and forwards it to the ESP.

```typescript
// src/index.ts
import type { ExecutionContext } from "@cloudflare/workers-types";

export interface Env {
  RELAY_SECRET: string;           // shared secret between relay and Worker
  RESEND_API_KEY: string;
  ALLOWED_FROM_DOMAINS: string;   // comma-separated: "example.com,marketing.example.com"
}

interface SmtpBridgePayload {
  from: string;
  to: string[];
  cc?: string[];
  bcc?: string[];
  subject: string;
  text?: string;
  html?: string;
  rawHeaders?: Record<string, string>;
}

function isAllowedFromDomain(from: string, allowedDomains: string): boolean {
  const domain = from.split("@")[1]?.toLowerCase();
  if (!domain) return false;
  return allowedDomains
    .split(",")
    .map((d) => d.trim().toLowerCase())
    .includes(domain);
}

async function sendViaResend(
  payload: SmtpBridgePayload,
  apiKey: string
): Promise<{ id: string }> {
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: payload.from,
      to: payload.to,
      cc: payload.cc,
      bcc: payload.bcc,
      subject: payload.subject,
      text: payload.text,
      html: payload.html,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`ESP error ${response.status}: ${body}`);
  }

  return response.json();
}

export default {
  async fetch(request: Request, env: Env, _ctx: ExecutionContext): Promise<Response> {
    // Only accept POST to /smtp/inbound
    if (request.method !== "POST" || new URL(request.url).pathname !== "/smtp/inbound") {
      return new Response("Not Found", { status: 404 });
    }

    // Authenticate relay with shared secret
    const authHeader = request.headers.get("X-Relay-Secret");
    if (!authHeader || authHeader !== env.RELAY_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    let payload: SmtpBridgePayload;
    try {
      payload = await request.json();
    } catch {
      return new Response("Invalid JSON body", { status: 400 });
    }

    // Validate sender domain
    if (!isAllowedFromDomain(payload.from, env.ALLOWED_FROM_DOMAINS)) {
      return new Response(
        JSON.stringify({ error: "sender_domain_not_allowed" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    try {
      const result = await sendViaResend(payload, env.RESEND_API_KEY);
      return Response.json({ ok: true, messageId: result.id }, { status: 200 });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      console.error("ESP delivery failure:", message);
      return Response.json({ error: message }, { status: 502 });
    }
  },
};
```

---

## Section 3: Node.js SMTP Relay (smtp-server)

A minimal Node.js relay using the `smtp-server` npm package receives SMTP connections and calls the Worker.

```typescript
// relay/server.ts
import { SMTPServer, SMTPServerDataStream, SMTPServerSession } from "smtp-server";
import { simpleParser, ParsedMail } from "mailparser";

const WORKER_URL = process.env.WORKER_URL!;       // https://smtp-relay.example.workers.dev
const RELAY_SECRET = process.env.RELAY_SECRET!;
const SMTP_AUTH_USER = process.env.SMTP_AUTH_USER!;
const SMTP_AUTH_PASS = process.env.SMTP_AUTH_PASS!;
const TLS_KEY = process.env.TLS_KEY_PATH!;
const TLS_CERT = process.env.TLS_CERT_PATH!;

import { readFileSync } from "fs";

const server = new SMTPServer({
  secure: false,          // use STARTTLS (port 587)
  key: readFileSync(TLS_KEY),
  cert: readFileSync(TLS_CERT),

  // Require AUTH LOGIN
  authOptional: false,
  onAuth(auth, _session, callback) {
    if (
      auth.username === SMTP_AUTH_USER &&
      auth.credentials.password === SMTP_AUTH_PASS
    ) {
      callback(null, { user: auth.username });
    } else {
      callback(new Error("Invalid credentials"));
    }
  },

  // Accept all RCPT TO addresses (Worker validates from-domain)
  onRcptTo(_address, _session, callback) {
    callback(); // accept
  },

  async onData(stream: SMTPServerDataStream, session: SMTPServerSession, callback) {
    try {
      const parsed: ParsedMail = await simpleParser(stream);

      const payload = {
        from: session.envelope.mailFrom
          ? (session.envelope.mailFrom as any).address
          : parsed.from?.value[0].address,
        to: session.envelope.rcptTo.map((r: any) => r.address),
        subject: parsed.subject ?? "(no subject)",
        text: parsed.text,
        html: parsed.html || undefined,
      };

      const response = await fetch(`${WORKER_URL}/smtp/inbound`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Relay-Secret": RELAY_SECRET,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const body = await response.text();
        throw new Error(`Worker rejected message: ${response.status} ${body}`);
      }

      callback(); // success — SMTP 250 OK
    } catch (err: any) {
      console.error("Relay error:", err.message);
      callback(new Error(`Temporary relay failure: ${err.message}`));
      // Returns SMTP 4xx — client will retry
    }
  },
});

server.listen(587, "0.0.0.0", () => {
  console.log("SMTP relay listening on port 587");
});

server.on("error", (err) => {
  console.error("SMTP server error:", err);
});
```

Install dependencies:

```bash
npm install smtp-server mailparser
npm install --save-dev @types/smtp-server @types/mailparser
```

---

## Section 4: Outbound SMTP via Workers Socket API

If you need the Worker itself to connect to an upstream SMTP server (e.g., forwarding to a smarthost), use the Workers Socket API:

```typescript
// src/outbound-smtp.ts
import { connect } from "cloudflare:sockets";

interface SmtpAuthConfig {
  host: string;
  port: number;
  username: string;
  password: string;
}

async function readLine(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    if (buffer.includes("\r\n")) break;
  }
  return buffer.trim();
}

export async function sendViaSmtp(
  config: SmtpAuthConfig,
  from: string,
  to: string[],
  rawMessage: string
): Promise<void> {
  const socket = connect({ hostname: config.host, port: config.port });
  const writer = socket.writable.getWriter();
  const reader = socket.readable.getReader();

  const send = async (line: string) => {
    await writer.write(new TextEncoder().encode(line + "\r\n"));
  };

  const expect = async (code: string): Promise<string> => {
    const response = await readLine(reader);
    if (!response.startsWith(code)) {
      throw new Error(`Expected ${code}, got: ${response}`);
    }
    return response;
  };

  try {
    await expect("220");          // Server greeting
    await send(`EHLO workers`);
    await expect("250");
    await send("STARTTLS");
    await expect("220");

    // Upgrade to TLS
    await socket.startTls();

    await send(`EHLO workers`);
    await expect("250");
    await send("AUTH LOGIN");
    await expect("334");
    await send(btoa(config.username));
    await expect("334");
    await send(btoa(config.password));
    await expect("235");          // Auth success

    await send(`MAIL FROM:<${from}>`);
    await expect("250");

    for (const recipient of to) {
      await send(`RCPT TO:<${recipient}>`);
      await expect("250");
    }

    await send("DATA");
    await expect("354");
    await send(rawMessage.replace(/^\./gm, "..") + "\r\n.");
    await expect("250");
    await send("QUIT");
  } finally {
    writer.releaseLock();
    reader.releaseLock();
    await socket.close();
  }
}
```

Note: `socket.startTls()` requires `compatibility_flags = ["nodejs_compat"]` in `wrangler.toml`.

---

## Section 5: Cloudflare Tunnel Pattern (smtp2http)

For environments where running a public SMTP server is not feasible, `smtp2http` converts inbound SMTP to HTTP callbacks and is exposed via a Cloudflare Tunnel.

```yaml
# smtp2http config: smtp2http.yaml
listen: "0.0.0.0:587"
callback_url: "https://smtp-relay.example.workers.dev/smtp/inbound"
auth:
  username: "relay-user"
  password: "${SMTP_AUTH_PASS}"
tls:
  enabled: true
  cert: "/etc/ssl/relay.crt"
  key: "/etc/ssl/relay.key"
headers:
  X-Relay-Secret: "${RELAY_SECRET}"
```

Expose it via tunnel:

```bash
# Install cloudflared
cloudflared tunnel create smtp-relay
cloudflared tunnel route dns smtp-relay smtp-relay.example.com

# config.yml
tunnel: smtp-relay
credentials-file: ~/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: smtp-relay.example.com
    service: tcp://localhost:587
  - service: http_status:404
```

---

## Anti-Patterns

- **Accepting all senders without domain validation** — an open relay will be exploited for spam within minutes. Always validate the envelope `MAIL FROM` domain against an allowlist.
- **Passing the RELAY_SECRET in a query parameter** — query parameters appear in server logs and Cloudflare analytics. Always use a custom HTTP header.
- **Blocking on large message bodies** — Workers have a 128 MB request body limit, but a 10 MB email will consume substantial CPU for base64 decoding. Strip or reject oversized attachments at the relay before calling the Worker.
- **Not returning SMTP 4xx on Worker 5xx** — if the Worker returns a 5xx, the relay must return an SMTP `4xx` (temporary failure) so the sending SMTP client retries. Mapping 5xx to `5xx` SMTP causes immediate NDR to the sender.
- **Running smtp-server as root** — port 587 requires privilege on Linux. Use `authbind`, `iptables REDIRECT`, or run on port 1587 and use NAT.

---

## Gotchas

- **Workers do not support `net` / TCP server sockets** — this is a hard platform constraint. The relay must be external (EC2, a Cloudflare Worker with a TCP server via Durable Objects is not currently supported for inbound connections).
- **TLS certificate for the relay** — SMTP clients expect a valid certificate on port 587. Use Let's Encrypt with `certbot` or Cloudflare's origin certificate for the relay host.
- **Message size limits** — Cloudflare Workers have a 128 MB request body limit, but the default `smtp-server` limit is 25 MB. Align both.
- **DKIM signing on the relay** — if you sign with DKIM at the relay before forwarding, the ESP may re-sign with its own key, breaking the original signature. Decide on a single signing point: either relay or ESP, not both.
- **Connection concurrency** — the relay may receive hundreds of simultaneous SMTP connections. The Worker's invocation concurrency is unlimited, but the ESP may rate-limit. Implement a semaphore or queue at the relay layer.

---

## Verification

```bash
# Test SMTP relay directly with swaks (Swiss Army Knife SMTP)
swaks \
  --to test@example.com \
  --from app@example.com \
  --server smtp-relay.example.com \
  --port 587 \
  --tls \
  --auth LOGIN \
  --auth-user relay-user \
  --auth-password "your-password" \
  --header "Subject: SMTP relay test" \
  --body "This email was sent through the Cloudflare Worker relay"

# Verify Worker received the payload
wrangler tail smtp-relay-worker --format=pretty

# Check the ESP sent it (Resend dashboard or API)
curl -H "Authorization: Bearer $RESEND_API_KEY" \
  "https://api.resend.com/emails?limit=5" | jq '.data[].to'
```

---

## Related

- `cloudflare-email-routing-workers.md` — routing inbound mail with Workers
- `smtp-requiretls-delivery-policy.md` — enforcing TLS on SMTP delivery
- `smtp-scram-sasl-channel-binding.md` — modern SMTP auth mechanisms
- `email-deliverability-cloudflare-worker-sender.md` — deliverability for Worker-originated mail
- `transactional-queue-cloudflare-queues.md` — queued delivery for reliability

---

## Sources

- [Cloudflare Workers — TCP Sockets (cloudflare:sockets)](https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/)
- [Cloudflare Tunnels documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
- [smtp-server npm package](https://nodemailer.com/extras/smtp-server/)
- [mailparser npm package](https://nodemailer.com/extras/mailparser/)
- [RFC 4954 — SMTP Service Extension for Authentication](https://datatracker.ietf.org/doc/html/rfc4954)
- [RFC 3207 — SMTP Service Extension for Secure SMTP over TLS](https://datatracker.ietf.org/doc/html/rfc3207)
- [swaks — Swiss Army Knife SMTP](https://www.jetmore.org/john/code/swaks/)
