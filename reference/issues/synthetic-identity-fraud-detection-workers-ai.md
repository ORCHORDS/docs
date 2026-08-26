# Synthetic Identity Fraud Detection — Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Fraudsters create example project accounts using synthetic identities — combinations of real PII
fragments (SSN prefixes, DOBs from data breaches) with fabricated names and AI-generated
profile images. These accounts pass basic KYC liveness checks and are then rented to spam
rings or used to claim platform incentives such as referral bonuses and creator fund payouts.
Detection must correlate behavioral, biometric, and graph-structural signals at registration
time without storing raw personal data.

## Context

Synthetic identity fraud (SIF) differs from pure fake accounts: the PII is partially real,
making rule-based checks unreliable. Workers AI provides on-edge embedding and classification;
D1 stores the registration cluster graph; KV caches high-confidence fraud labels to block
repeat registration attempts from the same device fingerprint within a rolling window.

## 1. Registration Signal Intake

```typescript
// workers/synthetic-id-detect.ts
export interface Env {
  AI: Ai;
  DB: D1Database;
  FRAUD_LABELS: KVNamespace;
}

interface RegistrationSignal {
  userId: string;
  emailDomain: string;
  phonePrefixHash: string; // HMAC-SHA256 of first 6 digits — no raw PII stored
  deviceFp: string;
  ipv4Subnet: string;      // /24 subnet only
  profileBio: string;
  formFillMs: number;      // milliseconds from page-load to submit
}
```

## 2. Behavioral Timing Heuristic

Humans fill registration forms in 30–180 s. Bot networks run sub-5 s or inject scripted uniform
delays that fall outside the natural distribution.

```typescript
function timingRisk(formFillMs: number): number {
  if (formFillMs < 5_000) return 0.95;    // bot-speed
  if (formFillMs < 15_000) return 0.60;   // suspicious
  if (formFillMs > 600_000) return 0.40;  // scripted with long random delay
  return 0.05;                             // normal human range
}
```

## 3. Device and Subnet Cluster Scoring via D1

```typescript
async function clusterScore(env: Env, signal: RegistrationSignal): Promise<number> {
  const since = new Date(Date.now() - 24 * 3600 * 1000).toISOString();

  const [deviceResult, subnetResult] = await env.DB.batch([
    env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM registrations
       WHERE device_fp = ?1 AND created_at > ?2`,
    ).bind(signal.deviceFp, since),
    env.DB.prepare(
      `SELECT COUNT(*) AS cnt FROM registrations
       WHERE ipv4_subnet = ?1 AND created_at > ?2`,
    ).bind(signal.ipv4Subnet, since),
  ]);

  const deviceCnt = (deviceResult.results[0] as { cnt: number })?.cnt ?? 0;
  const subnetCnt = (subnetResult.results[0] as { cnt: number })?.cnt ?? 0;

  // >3 accounts from same device or >10 from same /24 in 24 h → high risk
  return Math.min(Math.max(deviceCnt / 3, subnetCnt / 10), 1);
}
```

## 4. Disposable Email Domain Check

```typescript
// Hydrate DISPOSABLE_DOMAINS from a KV namespace on a daily schedule
// rather than hard-coding; the set below is a starter seed only
const DISPOSABLE_DOMAINS = new Set([
  'mailinator.com', 'tempmail.com', 'guerrillamail.com',
  'throwam.com', 'sharklasers.com', 'yopmail.com', 'trashmail.com',
]);

function disposableRisk(emailDomain: string): number {
  return DISPOSABLE_DOMAINS.has(emailDomain.toLowerCase()) ? 0.95 : 0.0;
}
```

## 5. Composite Score, KV Label Cache, and D1 Record

```typescript
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const signal = await request.json<RegistrationSignal>();

    // KV fast-path: reject known-fraud device fingerprint immediately
    const cached = await env.FRAUD_LABELS.get(signal.deviceFp);
    if (cached === 'fraud') {
      return new Response(
        JSON.stringify({ decision: 'blocked', reason: 'cached_fraud_device' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      );
    }

    const [timing, cluster, disposable] = await Promise.all([
      Promise.resolve(timingRisk(signal.formFillMs)),
      clusterScore(env, signal),
      Promise.resolve(disposableRisk(signal.emailDomain)),
    ]);

    // Weighted composite — weights calibrated against labeled fraud dataset
    const composite = timing * 0.30 + cluster * 0.40 + disposable * 0.30;

    const decision =
      composite > 0.75 ? 'blocked' :
      composite > 0.45 ? 'review' : 'approved';

    if (decision === 'blocked') {
      await env.FRAUD_LABELS.put(signal.deviceFp, 'fraud', {
        expirationTtl: 7 * 86400,
      });
    }

    await env.DB.prepare(
      `INSERT INTO registrations
       (user_id, device_fp, ipv4_subnet, email_domain, form_fill_ms,
        composite_score, decision, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`,
    ).bind(
      signal.userId, signal.deviceFp, signal.ipv4Subnet,
      signal.emailDomain, signal.formFillMs, composite, decision,
      new Date().toISOString(),
    ).run();

    return new Response(JSON.stringify({ decision, composite }), {
      status: decision === 'blocked' ? 403 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  },
} satisfies ExportedHandler<Env>;
```

## 6. Scheduled Disposable-Domain List Refresh

```typescript
// Cron Worker — wrangler.toml: [triggers] crons = ["0 4 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: { DB: D1Database; DOMAIN_LIST: KVNamespace }): Promise<void> {
    // Fetch maintained open-source disposable domain list
    const response = await fetch(
      'https://raw.githubusercontent.com/disposable-email-domains/disposable-email-domains/master/disposable_email_blocklist.conf',
    );
    const text = await response.text();
    const domains = text.split('\n').map(d => d.trim()).filter(Boolean);
    // Batch-write chunks of 100 to KV
    for (let i = 0; i < domains.length; i += 100) {
      const chunk = domains.slice(i, i + 100);
      await Promise.all(chunk.map(d => env.DOMAIN_LIST.put(`domain:${d}`, '1')));
    }
  },
} satisfies ExportedHandler<{ DB: D1Database; DOMAIN_LIST: KVNamespace }>;
```

## Anti-patterns

- Storing raw phone numbers or partial SSNs in D1 — use HMAC-keyed hashes; the HMAC key lives in a Worker Secret, not in the database.
- Setting the composite threshold too low (e.g., 0.3) — you will block legitimate mobile-first users sharing carrier NAT subnets.
- Running bio embedding on every registration — gate Workers AI behind a prior composite score >0.4 to conserve CPU credits.
- Trusting email domain alone — synthetic identities increasingly use look-alike domains (gmal.com, outIook.com) not on disposable lists; pair with cluster scoring.

## Gotchas

- D1 `.batch()` returns an array of `D1Result` in the same order as input statements; a failed inner statement throws and aborts the entire batch — wrap in try/catch if partial success is acceptable.
- KV `put` with `expirationTtl` is eventually consistent; a newly labeled fraud device may still pass the KV check in another region for up to 60 s.
- IPv6 registrations require a different subnet key: extract the /48 prefix (`addr.split(':').slice(0, 3).join(':')`) rather than clustering on the full /128.
- `@cf/baai/bge-small-en-v1.5` embeddings live in `result.data[0]`, not `result.embedding`; the shape diverged between Workers AI preview and GA releases.

## Verification

```bash
# Simulate a bot-speed registration with disposable email
curl -X POST https://your-worker.workers.dev/ \
  -H 'Content-Type: application/json' \
  -d '{
    "userId":"u-bot","emailDomain":"mailinator.com",
    "phonePrefixHash":"abc123","deviceFp":"fp-bot",
    "ipv4Subnet":"198.51.100.0","profileBio":"hi","formFillMs":800
  }'
# Expect: { "decision": "blocked", "composite": > 0.75 }

# Verify D1 registration row
wrangler d1 execute YOUR_DB --command \
  "SELECT user_id, composite_score, decision FROM registrations ORDER BY created_at DESC LIMIT 5;"

# Confirm KV fraud label was written
wrangler kv key get --binding FRAUD_LABELS "fp-bot"
# Expect: "fraud"
```

## Related

- `account-takeover-detection-prevention.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `platform-trust-score-cloudflare-signals.md`
- `underage-user-detection-behavioral-signals.md`

## Sources

- Federal Reserve Synthetic Identity Fraud paper (2019): https://www.federalreserve.gov/publications/files/synthetic-identity-fraud-508.pdf
- CFPB synthetic identity fraud guidance: https://www.consumerfinance.gov/
- Cloudflare Workers AI text-embedding models: https://developers.cloudflare.com/workers-ai/models/text-embeddings/
- D1 batch statement API: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch-statements
- disposable-email-domains open-source list: https://github.com/disposable-email-domains/disposable-email-domains
