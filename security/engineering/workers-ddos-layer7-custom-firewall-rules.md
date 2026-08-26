# Layer 7 DDoS Defence with Custom Firewall Rules in Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Your application is targeted by a layer-7 HTTP flood: thousands of requests per second from distributed IPs, all with valid TLS handshakes and syntactically correct HTTP. Cloudflare's managed DDoS rules fire too broadly or not at all for your traffic pattern. You need custom, application-aware mitigation that inspects request semantics, scores threat likelihood, and responds with graduated countermeasures (challenge, block, tarpit) — all without adding origin latency for legitimate users.

## Context

Cloudflare Workers run before origin and can implement request-scoring logic using Durable Objects for per-IP/per-user state, KV for blocklists, and the Workers AI or in-process heuristics for behavioural fingerprinting. Unlike WAF custom rules (which operate on Wireshark-style fields), Workers have full access to request bodies, timing, and JavaScript-evaluated heuristics. The goal is defence-in-depth: Cloudflare managed rules first, Workers scoring second, origin logic third.

## 1. Threat-Scoring Middleware

```typescript
// src/threat-score.ts
export interface ThreatContext {
  ip: string;
  asn: string | null;
  country: string | null;
  userAgent: string;
  path: string;
  method: string;
  referer: string | null;
  cfThreatScore: number; // 0-100, Cloudflare bot score if available
}

export function buildThreatContext(request: Request): ThreatContext {
  const cf = (request as any).cf ?? {};
  return {
    ip: request.headers.get("CF-Connecting-IP") ?? "unknown",
    asn: cf.asn ? String(cf.asn) : null,
    country: cf.country ?? null,
    userAgent: request.headers.get("user-agent") ?? "",
    path: new URL(request.url).pathname,
    method: request.method,
    referer: request.headers.get("referer"),
    cfThreatScore: typeof cf.botManagement?.score === "number"
      ? cf.botManagement.score
      : 100, // assume worst if unavailable
  };
}

export function heuristicScore(ctx: ThreatContext): number {
  let score = 0;

  // Empty or missing User-Agent
  if (!ctx.userAgent || ctx.userAgent.length < 5) score += 30;

  // Known bad UA fragments
  const badUAs = ["zgrab", "masscan", "nuclei", "sqlmap", "nikto", "python-requests/2."];
  if (badUAs.some((ua) => ctx.userAgent.toLowerCase().includes(ua))) score += 50;

  // No referer on deep paths (common for automated scanners)
  if (!ctx.referer && ctx.path.split("/").length > 3) score += 10;

  // High-sensitivity endpoints probed with non-standard methods
  const sensitivePaths = ["/admin", "/api/internal", "/.env", "/wp-admin"];
  if (sensitivePaths.some((p) => ctx.path.startsWith(p))) score += 20;
  if (["TRACE", "CONNECT", "OPTIONS"].includes(ctx.method) && ctx.path !== "/") score += 15;

  // Cloudflare bot management score (0=definitely bot, 100=definitely human)
  if (ctx.cfThreatScore < 30) score += 40;
  else if (ctx.cfThreatScore < 60) score += 15;

  return Math.min(score, 100);
}
```

## 2. Per-IP Rate State in Durable Objects

```typescript
// src/ip-rate-do.ts
import { DurableObject } from "cloudflare:workers";

interface WindowState {
  count: number;
  windowStart: number;
  blockedUntil: number;
  strikes: number;
}

export class IPRateDO extends DurableObject {
  private state: WindowState = {
    count: 0,
    windowStart: Date.now(),
    blockedUntil: 0,
    strikes: 0,
  };

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const threshold = parseInt(url.searchParams.get("threshold") ?? "200");
    const windowMs = parseInt(url.searchParams.get("window") ?? "60000");

    const now = Date.now();

    // Still in block period
    if (now < this.state.blockedUntil) {
      return Response.json({ action: "block", retryAfter: Math.ceil((this.state.blockedUntil - now) / 1000) });
    }

    // Reset window
    if (now - this.state.windowStart > windowMs) {
      this.state.count = 0;
      this.state.windowStart = now;
    }

    this.state.count++;

    if (this.state.count > threshold) {
      this.state.strikes++;
      // Exponential back-off: 1min, 5min, 30min, 24h
      const blockDurations = [60_000, 300_000, 1_800_000, 86_400_000];
      const duration = blockDurations[Math.min(this.state.strikes - 1, blockDurations.length - 1)];
      this.state.blockedUntil = now + duration;
      return Response.json({ action: "block", retryAfter: Math.ceil(duration / 1000) });
    }

    if (this.state.count > threshold * 0.8) {
      return Response.json({ action: "challenge" });
    }

    return Response.json({ action: "allow", remaining: threshold - this.state.count });
  }
}
```

## 3. Graduated Response Logic

```typescript
// src/mitigate.ts
export type MitigationAction = "allow" | "challenge" | "tarpit" | "block";

export async function determineMitigation(
  threatScore: number,
  rateAction: string
): Promise<MitigationAction> {
  if (rateAction === "block") return "block";
  if (threatScore >= 70) return "block";
  if (threatScore >= 50 || rateAction === "challenge") return "challenge";
  if (threatScore >= 30) return "tarpit";
  return "allow";
}

export function buildMitigationResponse(action: MitigationAction, retryAfter?: number): Response | null {
  switch (action) {
    case "block":
      return new Response(
        JSON.stringify({ error: "Access denied" }),
        {
          status: 403,
          headers: {
            "Content-Type": "application/json",
            "Retry-After": String(retryAfter ?? 300),
            "X-Robots-Tag": "noindex",
          },
        }
      );
    case "challenge":
      // In production: redirect to Cloudflare Turnstile challenge page
      return Response.redirect("https://example.com/challenge?origin=" +
        encodeURIComponent("ORIGINAL_URL"), 302);
    case "tarpit":
      // Slow down automated clients by holding the response open briefly
      // Workers don't support true tarpitting, but we can add a synthetic delay
      return null; // handled in the fetch handler with a delayed forward
    case "allow":
      return null;
  }
}
```

## 4. Main Worker with Integrated Mitigation

```typescript
// src/index.ts
import { buildThreatContext, heuristicScore } from "./threat-score";
import { determineMitigation, buildMitigationResponse } from "./mitigate";

export { IPRateDO } from "./ip-rate-do";

interface Env {
  IP_RATE: DurableObjectNamespace;
  BLOCKLIST: KVNamespace;       // pre-populated bad IP CIDR list
  TARPIT_DELAY_MS: string;      // env var, e.g. "2000"
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const ctx = buildThreatContext(request);

    // 1. Static blocklist check (KV — fast, eventually consistent)
    const blocked = await env.BLOCKLIST.get(ctx.ip);
    if (blocked) {
      return new Response(JSON.stringify({ error: "Blocked" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    }

    // 2. Heuristic threat scoring
    const score = heuristicScore(ctx);

    // 3. Per-IP rate limit via DO (consistent)
    const doId = env.IP_RATE.idFromName(ctx.ip);
    const stub = env.IP_RATE.get(doId);
    const rateResp = await stub.fetch(
      `https://rate/?threshold=200&window=60000`,
      { method: "GET" }
    );
    const { action: rateAction, retryAfter } = await rateResp.json<{
      action: string;
      retryAfter?: number;
    }>();

    // 4. Graduated response
    const mitigation = await determineMitigation(score, rateAction);
    const mitigationResp = buildMitigationResponse(mitigation, retryAfter);
    if (mitigationResp) return mitigationResp;

    // 5. Tarpit: hold request briefly to exhaust attacker concurrency
    if (mitigation === "tarpit") {
      await new Promise((resolve) =>
        setTimeout(resolve, parseInt(env.TARPIT_DELAY_MS ?? "2000"))
      );
    }

    // 6. Forward to origin
    return fetch(request);
  },
};
```

## 5. Populating the Blocklist via Wrangler

```bash
# Add a known-bad IP to KV blocklist
wrangler kv key put --namespace-id=NAMESPACE_ID "203.0.113.42" "abuse"

# Bulk import from threat feed (example — adapt for your feed format)
cat abuse_ips.txt | while read ip; do
  wrangler kv key put --namespace-id=NAMESPACE_ID "$ip" "threat-feed"
done
```

## Anti-patterns

- **Blocking on heuristic score alone without rate context.** A mobile carrier NAT may share one IP; score alone can false-positive; combine with request rate.
- **Logging full request bodies for DDoS debugging.** L7 floods may contain PII payloads; log only headers and metadata.
- **Tarpitting CPU-bound work inside a Worker.** `setTimeout` in Workers uses the event-loop and does not consume CPU; do not spin in a busy loop.
- **Using KV for per-IP rate limiting.** KV is eventually consistent; two replicas can both allow a request above threshold; use DOs for rate state.
- **Serving HTML challenge pages with CSP nonces from a blocked-IP path.** Attackers can harvest nonces for later use; challenge redirects must use the Cloudflare Turnstile or similar external challenge.

## Gotchas

- Durable Objects are region-pinned; requests from diverse global IPs to the same DO instance incur cross-region latency. Use `jurisdiction: "eu"` or Smart Placement for latency control.
- `(request as any).cf.botManagement.score` requires Cloudflare's Bot Management add-on; it is absent on lower tiers — always default to a high score if the field is missing.
- Workers have a 10 ms CPU time limit on the free tier (50 ms on paid); keep mitigation logic lean; defer heavy analytics to Tail Workers.
- KV blocklists are eventually consistent with up to 60 s propagation; do not rely on them for real-time blocking of actively attacking IPs — use DO state for that.
- `setTimeout` in Workers uses wall-clock time but the isolate may be preempted; for tarpit purposes, actual delay may be shorter under high load.

## Verification

```bash
# Simulate high rate from one IP using hey (HTTP load tool)
hey -n 500 -c 50 -H "CF-Connecting-IP: 10.0.0.1" https://api.example.com/

# Expect 403 after threshold is crossed
# Check DO state via Tail Worker logs or wrangler tail
wrangler tail --format=pretty

# Verify blocklist entry
wrangler kv key get --namespace-id=NAMESPACE_ID "203.0.113.42"
```

## Related

- `ddos-mitigation-strategies.md`
- `rate-limiting-ddos-defense-layers.md`
- `cloudflare-rate-limiting-v2-api-abuse-prevention.md`
- `token-bucket-rate-limiting-durable-objects.md`
- `cloudflare-bot-management-abuse-prevention.md`

## Sources

- Cloudflare DDoS protection overview — https://developers.cloudflare.com/ddos-protection/
- Cloudflare Workers Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare Bot Management — https://developers.cloudflare.com/bots/
- OWASP Layer 7 DDoS — https://owasp.org/www-community/attacks/Denial_of_Service
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
