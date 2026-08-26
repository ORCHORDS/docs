# Fraud Scoring Pipeline: Velocity Checks, Device Fingerprinting, and Workers AI Classification

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Card testing attacks succeed in bursts: dozens of `$0` or `$1` authorization attempts from the same IP or fingerprint cluster hit your checkout before a single Stripe Radar rule fires. By the time Radar blocks the card, you've already paid `$0.05–0.09` per declined authorization and your dispute rate is climbing. You need a pre-authorization fraud gate running at the edge — before the Stripe API is called — that combines velocity counters, device signals, and ML inference in under 50 ms.

---

## Context

The pipeline has three layers:

1. **Velocity checks** — Cloudflare KV counters keyed by IP, fingerprint, and email domain, evaluated in the Worker before any Stripe call.
2. **Device fingerprinting** — Client-side signals (canvas hash, WebGL renderer, audio fingerprint, timezone) collected via a lightweight inline script and sent as an opaque `fp` token with the checkout POST.
3. **Workers AI classification** — A small `@cf/meta/llama-3.1-8b-instruct` or `@cf/mistral/mistral-7b-instruct-v0.1` model (or a purpose-trained text-classification model) takes a JSON feature vector and returns a fraud probability score.

Actions at each threshold:
- Score 0–0.3: allow
- Score 0.3–0.6: allow but flag for review + send `metadata.fraud_flag=review` to Stripe
- Score 0.6–0.8: require CAPTCHA challenge (Cloudflare Turnstile)
- Score > 0.8: block at edge, no Stripe API call

---

## 1. Velocity Check Implementation with KV Counters

```typescript
// src/fraud/velocity.ts
import type { KVNamespace } from "@cloudflare/workers-types";

export interface VelocityResult {
  ipCount: number;
  fpCount: number;
  emailDomainCount: number;
  blocked: boolean;
  reason?: string;
}

const THRESHOLDS = {
  ip: { window: 60, limit: 5 },          // 5 attempts per IP per 60s
  fingerprint: { window: 300, limit: 10 }, // 10 per fingerprint per 5min
  emailDomain: { window: 3600, limit: 50 }, // 50 per domain per hour
};

async function increment(kv: KVNamespace, key: string, windowSecs: number): Promise<number> {
  const existing = await kv.get(key);
  const count = existing ? parseInt(existing, 10) + 1 : 1;
  await kv.put(key, String(count), { expirationTtl: windowSecs });
  return count;
}

export async function checkVelocity(
  kv: KVNamespace,
  ip: string,
  fingerprint: string,
  emailDomain: string
): Promise<VelocityResult> {
  const now = Math.floor(Date.now() / 1000);
  const ipWindow = Math.floor(now / THRESHOLDS.ip.window);
  const fpWindow = Math.floor(now / THRESHOLDS.fingerprint.window);
  const edWindow = Math.floor(now / THRESHOLDS.emailDomain.window);

  const [ipCount, fpCount, emailDomainCount] = await Promise.all([
    increment(kv, `vel:ip:${ip}:${ipWindow}`, THRESHOLDS.ip.window * 2),
    increment(kv, `vel:fp:${fingerprint}:${fpWindow}`, THRESHOLDS.fingerprint.window * 2),
    increment(kv, `vel:ed:${emailDomain}:${edWindow}`, THRESHOLDS.emailDomain.window * 2),
  ]);

  if (ipCount > THRESHOLDS.ip.limit) {
    return { ipCount, fpCount, emailDomainCount, blocked: true, reason: "ip_velocity" };
  }
  if (fpCount > THRESHOLDS.fingerprint.limit) {
    return { ipCount, fpCount, emailDomainCount, blocked: true, reason: "fp_velocity" };
  }
  if (emailDomainCount > THRESHOLDS.emailDomain.limit) {
    return { ipCount, fpCount, emailDomainCount, blocked: true, reason: "email_domain_velocity" };
  }

  return { ipCount, fpCount, emailDomainCount, blocked: false };
}
```

Window-keying by `Math.floor(now / windowSecs)` creates fixed tumbling windows. Each key is written with TTL = `2 * window` so stale buckets expire automatically without a cleanup job.

---

## 2. Client-Side Device Fingerprinting

Collect signals in the browser before form submission. The goal is a stable, opaque identifier — not PII.

```typescript
// public/fp.ts  (bundled inline into checkout page)
async function buildFingerprint(): Promise<string> {
  const signals: string[] = [];

  // Canvas fingerprint
  try {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    ctx.textBaseline = "top";
    ctx.font = "14px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("Cloudflare Workers 🔒", 2, 15);
    signals.push(canvas.toDataURL().slice(-40));
  } catch {
    signals.push("canvas:na");
  }

  // WebGL renderer
  try {
    const gl = document.createElement("canvas").getContext("webgl")!;
    const dbgInfo = gl.getExtension("WEBGL_debug_renderer_info")!;
    signals.push(gl.getParameter(dbgInfo.UNMASKED_RENDERER_WEBGL).slice(0, 30));
  } catch {
    signals.push("webgl:na");
  }

  // Timezone
  signals.push(Intl.DateTimeFormat().resolvedOptions().timeZone);

  // Screen geometry
  signals.push(`${screen.width}x${screen.height}x${screen.colorDepth}`);

  // Platform
  signals.push(navigator.platform.slice(0, 10));

  // Audio fingerprint (subtle timing)
  try {
    const ac = new OfflineAudioContext(1, 44100, 44100);
    const osc = ac.createOscillator();
    const analyser = ac.createAnalyser();
    osc.connect(analyser);
    analyser.connect(ac.destination);
    osc.start(0);
    const buf = await ac.startRendering();
    const slice = Array.from(buf.getChannelData(0).slice(4500, 4510));
    signals.push(slice.map((n) => n.toFixed(6)).join("").slice(0, 20));
  } catch {
    signals.push("audio:na");
  }

  const combined = signals.join("|");
  // Hash to produce a stable 16-char token
  const encoder = new TextEncoder();
  const data = encoder.encode(combined);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

// Attach to checkout form
document.addEventListener("DOMContentLoaded", async () => {
  const fp = await buildFingerprint();
  const input = document.getElementById("fp-token") as HTMLInputElement;
  if (input) input.value = fp;
});
```

The fingerprint is intentionally non-reversible. It identifies device clusters for velocity checks — it is not used to track individuals across unrelated sessions.

---

## 3. Feature Vector Construction

```typescript
// src/fraud/features.ts
import { VelocityResult } from "./velocity";

export interface FraudFeatures {
  ipVelocity: number;        // normalized 0–1
  fpVelocity: number;
  emailDomainVelocity: number;
  isProxyOrVpn: number;      // 0 or 1 from CF-IPThreatScore
  isTor: number;             // 0 or 1 from CF-IPThreatScore
  countryMismatch: number;   // billing country vs IP country
  emailIsDisposable: number; // known disposable domain
  amountCents: number;       // normalized (log scale)
  hourOfDay: number;         // 0–23, normalized 0–1
  dayOfWeek: number;         // 0–6, normalized 0–1
}

const DISPOSABLE_DOMAINS = new Set([
  "mailinator.com", "guerrillamail.com", "10minutemail.com",
  "tempmail.com", "throwaway.email", "yopmail.com",
]);

export function buildFeatures(
  request: Request,
  velocity: VelocityResult,
  emailDomain: string,
  billingCountry: string,
  amountCents: number
): FraudFeatures {
  const ipThreat = parseInt(request.headers.get("CF-IPThreatScore") ?? "0", 10);
  const ipCountry = request.headers.get("CF-IPCountry") ?? "XX";
  const now = new Date();

  return {
    ipVelocity: Math.min(velocity.ipCount / 10, 1),
    fpVelocity: Math.min(velocity.fpCount / 20, 1),
    emailDomainVelocity: Math.min(velocity.emailDomainCount / 100, 1),
    isProxyOrVpn: ipThreat > 14 ? 1 : 0,
    isTor: ipThreat > 49 ? 1 : 0,
    countryMismatch: billingCountry !== ipCountry && billingCountry !== "XX" ? 1 : 0,
    emailIsDisposable: DISPOSABLE_DOMAINS.has(emailDomain.toLowerCase()) ? 1 : 0,
    amountCents: Math.log1p(amountCents) / Math.log1p(100000), // normalize to 0–1
    hourOfDay: now.getUTCHours() / 23,
    dayOfWeek: now.getUTCDay() / 6,
  };
}
```

`CF-IPThreatScore` is a Cloudflare-provided header (0–100) available on all Worker requests in production. Scores > 14 indicate anonymizing proxies; > 49 indicate known threats.

---

## 4. Workers AI Classification

```typescript
// src/fraud/classify.ts
import type { Ai } from "@cloudflare/workers-types";
import type { FraudFeatures } from "./features";

export interface ClassificationResult {
  score: number;       // 0–1 fraud probability
  confidence: number;  // model confidence
  label: "low" | "medium" | "high" | "block";
}

// Prompt template for text-generation models used as classifiers
function buildPrompt(features: FraudFeatures): string {
  return `You are a payment fraud classifier. Given these normalized risk features (all values 0–1), output ONLY a JSON object with keys "fraud_probability" (float 0–1) and "confidence" (float 0–1). No explanation.

Features:
- ip_velocity: ${features.ipVelocity.toFixed(3)}
- fp_velocity: ${features.fpVelocity.toFixed(3)}
- email_domain_velocity: ${features.emailDomainVelocity.toFixed(3)}
- is_proxy_or_vpn: ${features.isProxyOrVpn}
- is_tor: ${features.isTor}
- country_mismatch: ${features.countryMismatch}
- email_is_disposable: ${features.emailIsDisposable}
- amount_normalized: ${features.amountCents.toFixed(3)}
- hour_of_day_normalized: ${features.hourOfDay.toFixed(3)}
- day_of_week_normalized: ${features.dayOfWeek.toFixed(3)}

JSON:`;
}

export async function classifyFraud(
  ai: Ai,
  features: FraudFeatures
): Promise<ClassificationResult> {
  // Use Workers AI text generation as a zero-shot classifier
  const response = await ai.run("@cf/mistral/mistral-7b-instruct-v0.1", {
    prompt: buildPrompt(features),
    max_tokens: 64,
    temperature: 0.0, // deterministic output
  });

  let score = 0.5;
  let confidence = 0.5;

  try {
    const text = (response as { response: string }).response.trim();
    // Extract JSON from the model output (it may add surrounding text)
    const match = text.match(/\{[^}]+\}/);
    if (match) {
      const parsed = JSON.parse(match[0]);
      score = Math.max(0, Math.min(1, Number(parsed.fraud_probability ?? 0.5)));
      confidence = Math.max(0, Math.min(1, Number(parsed.confidence ?? 0.5)));
    }
  } catch {
    // Model output was not valid JSON — treat as medium risk
    score = 0.5;
    confidence = 0.3;
  }

  const label: ClassificationResult["label"] =
    score > 0.8 ? "block" :
    score > 0.6 ? "high" :
    score > 0.3 ? "medium" : "low";

  return { score, confidence, label };
}
```

For production at scale, replace the LLM with a purpose-trained binary classifier model uploaded to Workers AI. The LLM approach works well for prototyping and low-volume traffic (< 10k requests/day) without requiring training data.

---

## 5. Pipeline Integration in the Checkout Worker

```typescript
// src/worker.ts
import Stripe from "stripe";
import { checkVelocity } from "./fraud/velocity";
import { buildFeatures } from "./fraud/features";
import { classifyFraud } from "./fraud/classify";
import { getSession } from "./auth";

interface Env {
  FRAUD_KV: KVNamespace;
  AI: Ai;
  STRIPE_SECRET_KEY: string;
  JWT_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/checkout/init") {
      return new Response("Not Found", { status: 404 });
    }

    const session = await getSession(request, env.JWT_SECRET);
    if (!session) return new Response(null, { status: 401 });

    const body = await request.json<{
      fingerprint: string;
      email: string;
      billingCountry: string;
      amountCents: number;
    }>();

    const ip = request.headers.get("CF-Connecting-IP") ?? "0.0.0.0";
    const emailDomain = body.email.split("@")[1] ?? "unknown";

    // Layer 1: Velocity
    const velocity = await checkVelocity(env.FRAUD_KV, ip, body.fingerprint, emailDomain);
    if (velocity.blocked) {
      return new Response(
        JSON.stringify({ error: "rate_limited", reason: velocity.reason }),
        { status: 429, headers: { "Content-Type": "application/json" } }
      );
    }

    // Layer 2: Feature vector
    const features = buildFeatures(
      request, velocity, emailDomain, body.billingCountry, body.amountCents
    );

    // Layer 3: AI classification
    const classification = await classifyFraud(env.AI, features);

    if (classification.label === "block") {
      // Log for review but return a generic error to avoid fingerprinting
      await env.FRAUD_KV.put(
        `block:${ip}:${Date.now()}`,
        JSON.stringify({ ip, fingerprint: body.fingerprint, score: classification.score }),
        { expirationTtl: 86400 }
      );
      return new Response(
        JSON.stringify({ error: "payment_declined" }),
        { status: 402, headers: { "Content-Type": "application/json" } }
      );
    }

    // Proceed to Stripe
    const stripe = new Stripe(env.STRIPE_SECRET_KEY);
    const paymentIntent = await stripe.paymentIntents.create({
      amount: body.amountCents,
      currency: "usd",
      customer: session.stripeCustomerId,
      metadata: {
        fraud_score: String(classification.score.toFixed(3)),
        fraud_label: classification.label,
        ip_velocity: String(velocity.ipCount),
        fp_velocity: String(velocity.fpCount),
        device_fingerprint: body.fingerprint.slice(0, 8) + "...", // truncated for PCI
      },
    });

    return new Response(
      JSON.stringify({
        clientSecret: <redacted-secret>
        fraudLabel: classification.label, // client can show CAPTCHA for "medium"
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## Anti-patterns

- **Relying solely on Stripe Radar.** Radar fires after the API call — you've already paid the per-authorization fee. Edge-side blocking is the only way to eliminate costs from card testing.
- **Sharing velocity counters across KV namespaces.** Use a dedicated `FRAUD_KV` namespace so its TTL management doesn't interfere with other caches.
- **Storing the full device fingerprint in Stripe metadata.** Stripe metadata is visible to anyone with API read access. Store a truncated or hashed version.
- **Using the AI model output directly without bounds-clamping.** LLMs can output values outside `[0, 1]` or non-JSON. Always clamp and default to medium risk on parse failure.
- **Blocking on AI classification for every request in high-traffic scenarios.** Gate AI classification behind velocity: only invoke the model when `velocity.ipCount > 2 || features.isProxyOrVpn`.
- **Treating `CF-IPThreatScore` as a sole blocker.** Many legitimate users access from VPNs. Use it as one signal among many, not a hard block.

---

## Gotchas

- **Workers AI billing.** `@cf/mistral/mistral-7b-instruct-v0.1` costs neurons (Workers AI units). At default limits each request uses ~1 neuron for a 64-token response. Budget accordingly or cache scores for identical feature vectors.
- **KV write latency under burst.** During a card testing burst you may have hundreds of simultaneous `increment()` calls. KV writes are eventually consistent — two concurrent increments from different edge nodes can both read `count=1` and both write `2`. This is acceptable: velocity limits are soft guards, not hard rate limiters. For hard limits, use Durable Objects instead.
- **`CF-IPThreatScore` is only available on Workers (not Pages).** Ensure your fraud Worker is deployed as a standalone Worker, not embedded in a Pages Function.
- **Device fingerprints can be spoofed.** They add friction for unsophisticated attackers (most card testers use cheap scripts) but are not cryptographic proof of identity.
- **The GDPR / CCPA surface.** Canvas fingerprinting may require consent under some interpretations of ePrivacy. Consult legal before deploying in the EU; consider whether a session-scoped nonce-based identifier is sufficient for your threat model.

---

## Verification

```bash
# 1. Simulate IP velocity breach (6 requests in 60s)
for i in $(seq 1 6); do
  curl -s -X POST https://your-worker.example.com/checkout/init \
    -H "CF-Connecting-IP: 1.2.3.4" \
    -H "CF-IPCountry: US" \
    -H "Cookie: __sess=<test_jwt>" \
    -H "Content-Type: application/json" \
    -d '{"fingerprint":"aaaa1111","email":"test@gmail.com","billingCountry":"US","amountCents":100}' \
  | jq '.error'
done
# First 5: null (success), 6th: "rate_limited"

# 2. Simulate VPN signal
curl -X POST https://your-worker.example.com/checkout/init \
  -H "CF-Connecting-IP: 5.6.7.8" \
  -H "CF-IPThreatScore: 20" \
  -H "CF-IPCountry: RU" \
  -H "Cookie: __sess=<test_jwt>" \
  -H "Content-Type: application/json" \
  -d '{"fingerprint":"bbbb2222","email":"test@mailinator.com","billingCountry":"US","amountCents":100}' \
  | jq '.fraudLabel'
# Expect: "high" or "block" due to disposable email + VPN + country mismatch

# 3. Inspect KV velocity counters
npx wrangler kv:key list --namespace-id=<FRAUD_KV_ID> --prefix="vel:ip:1.2.3.4" | jq '.[].name'

# 4. Check Stripe Payment Intent metadata
stripe payment_intents list --api-key=sk_test_... | \
  jq '.data[0].metadata | {fraud_score, fraud_label, ip_velocity}'
```

---

## Related

- `velocity-fraud-checks.md` — velocity check fundamentals without Workers AI
- `payment-fraud-detection-velocity-checks.md` — D1-backed velocity implementation
- `ai-ml-fraud-risk-scoring.md` — ML model selection and feature engineering for fraud
- `stripe-radar-fraud-rules.md` — Stripe-native rules as a downstream complement
- `card-testing-attack-prevention.md` — defense strategies for card testing specifically
- `pci-dss-saq-a-compliance.md` — PCI implications of storing fraud signals

---

## Sources

- Cloudflare Workers AI documentation: https://developers.cloudflare.com/workers-ai/
- Cloudflare KV documentation: https://developers.cloudflare.com/kv/
- Cloudflare `CF-IPThreatScore` header reference: https://developers.cloudflare.com/fundamentals/reference/http-request-headers/#cf-ipthreat-score
- Stripe Radar documentation: https://docs.stripe.com/radar
- FingerprintJS open-source library (for production device fingerprinting): https://github.com/fingerprintjs/fingerprintjs
- OWASP Testing Guide — Client Side Fingerprinting: https://owasp.org/www-project-web-security-testing-guide/
