# Ban Evasion Detection via Device Fingerprinting in D1

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Suspended users on an anonymous platform create new accounts and continue abusive behaviour because account bans carry no persistent identifier. Device fingerprinting correlates new registrations with previously banned sessions using stable browser and network signals.

## Context
On anonymous platforms there is no username or verified identity to block. Banned users simply clear cookies, switch incognito mode, or use a new email to re-register. A multi-signal fingerprint — combining Cloudflare request metadata, canvas/font entropy from a lightweight client script, and behavioural cadence — is hashed and stored in D1. On each new registration, the fingerprint is compared against a ban list. Matches above a confidence threshold block registration or apply immediate shadow restrictions.

## Client-Side Signal Collection

A small inline script collects browser entropy signals at registration time and POSTs a fingerprint payload alongside the registration form. No full canvas image is sent — only its hash.

```typescript
// client-side (inlined in registration page — not a Worker)
async function collectFingerprint(): Promise<string> {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d")!;
  ctx.textBaseline = "top";
  ctx.font = "14px Arial";
  ctx.fillText("BanEvade☃😀", 2, 2);
  const canvasData = canvas.toDataURL();

  const signals = {
    ua: navigator.userAgent,
    lang: navigator.language,
    tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
    screen: `${screen.width}x${screen.height}x${screen.colorDepth}`,
    cores: navigator.hardwareConcurrency,
    mem: (navigator as any).deviceMemory ?? 0,
    plugins: Array.from(navigator.plugins).map((p) => p.name).join(","),
    canvasHash: await sha256(canvasData),
    fonts: await probeFonts(),
  };

  return sha256(JSON.stringify(signals));
}

async function sha256(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
```

## Cloudflare-Side Signal Enrichment

The Worker enriches the client fingerprint with Cloudflare request metadata: AS number, IP /24 subnet (not the full IP for privacy), Turnstile token score, and CF-IPCountry. These signals are combined into a composite fingerprint hash.

```typescript
// worker: registration-gate.ts
export interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
  TURNSTILE_SECRET: string;
}

interface RegistrationPayload {
  clientFingerprint: string;
  turnstileToken: string;
  // ... other registration fields
}

async function buildCompositeFingerprint(
  req: Request,
  clientFp: string
): Promise<string> {
  const cf = req.cf as Record<string, string | number | undefined>;
  const ipHeader = req.headers.get("CF-Connecting-IP") ?? "0.0.0.0";
  const subnet = ipHeader.split(".").slice(0, 3).join(".") + ".0"; // /24

  const signals = {
    clientFp,
    asn: cf?.asn ?? 0,
    subnet,
    country: cf?.country ?? "XX",
    tlsVersion: cf?.tlsVersion ?? "",
  };

  const bytes = new TextEncoder().encode(JSON.stringify(signals));
  const buf = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const body = await req.json<RegistrationPayload>();

    // Validate Turnstile token
    const tsRes = await fetch(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
      {
        method: "POST",
        body: JSON.stringify({
          secret: env.TURNSTILE_SECRET,
          response: body.turnstileToken,
        }),
        headers: { "Content-Type": "application/json" },
      }
    );
    const ts = await tsRes.json<{ success: boolean; score?: number }>();
    if (!ts.success || (ts.score !== undefined && ts.score < 0.5)) {
      return new Response(
        JSON.stringify({ error: "bot_challenge_failed" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    const composite = await buildCompositeFingerprint(req, body.clientFingerprint);
    const evaded = await checkBanList(composite, body.clientFingerprint, env);

    if (evaded.blocked) {
      await env.DB.prepare(
        `INSERT INTO evasion_attempts (fingerprint, composite, detected_at, original_ban_id)
         VALUES (?, ?, ?, ?)`
      ).bind(
        body.clientFingerprint,
        composite,
        new Date().toISOString(),
        evaded.originalBanId
      ).run();

      return new Response(
        JSON.stringify({ error: "registration_denied" }),
        { status: 403, headers: { "Content-Type": "application/json" } }
      );
    }

    return proceedWithRegistration(body, composite, env);
  },
};
```

## Ban List Lookup with Fuzzy Matching

Exact fingerprint matches catch naive evasions. A fuzzy lookup checks whether any component signal (client FP or subnet) individually appears in the ban list, enabling detection even when the user rotates one signal.

```typescript
async function checkBanList(
  composite: string,
  clientFp: string,
  env: Env
): Promise<{ blocked: boolean; originalBanId?: string }> {
  // Exact composite match
  const exact = await env.DB.prepare(
    `SELECT ban_id FROM ban_fingerprints
     WHERE composite_hash = ? AND active = 1 LIMIT 1`
  ).bind(composite).first<{ ban_id: string }>();
  if (exact) return { blocked: true, originalBanId: exact.ban_id };

  // Fuzzy: client fingerprint alone matches (user changed network)
  const fuzzy = await env.DB.prepare(
    `SELECT ban_id FROM ban_fingerprints
     WHERE client_hash = ? AND active = 1 LIMIT 1`
  ).bind(clientFp).first<{ ban_id: string }>();
  if (fuzzy) return { blocked: true, originalBanId: fuzzy.ban_id };

  return { blocked: false };
}
```

## Ban Record Creation on Account Suspension

When the Trust & Safety team suspends an account, its stored fingerprints are written to the ban list so future evasion attempts are caught.

```typescript
// Called from account suspension workflow
export async function recordBanFingerprints(
  accountId: string,
  banId: string,
  env: Env
): Promise<void> {
  const { results } = await env.DB.prepare(
    `SELECT client_hash, composite_hash
     FROM registration_fingerprints
     WHERE account_id = ?`
  ).bind(accountId).all<{ client_hash: string; composite_hash: string }>();

  const stmts = results.map((fp) =>
    env.DB.prepare(
      `INSERT OR IGNORE INTO ban_fingerprints
       (ban_id, account_id, client_hash, composite_hash, active, created_at)
       VALUES (?, ?, ?, ?, 1, ?)`
    ).bind(banId, accountId, fp.client_hash, fp.composite_hash, new Date().toISOString())
  );

  await env.DB.batch(stmts);
}
```

## Evasion Trend Dashboard Query

A D1 query surfaces the highest-evasion offenders — accounts that were banned and have the most subsequent evasion attempts detected — for escalated enforcement.

```typescript
export async function topEvasionOffenders(
  env: Env,
  limit = 20
): Promise<Response> {
  const { results } = await env.DB.prepare(
    `SELECT bf.account_id, COUNT(ea.rowid) AS evasion_count, MAX(ea.detected_at) AS last_attempt
     FROM evasion_attempts ea
     JOIN ban_fingerprints bf ON ea.original_ban_id = bf.ban_id
     GROUP BY bf.account_id
     ORDER BY evasion_count DESC
     LIMIT ?`
  ).bind(limit).all();

  return Response.json(results);
}
```

## Anti-patterns
- Storing raw IP addresses in fingerprints — use /24 subnets or ASN to reduce privacy liability while retaining network-level signal
- Treating the client fingerprint as the sole truth — client-side signals are fully attacker-controlled; always combine with Cloudflare-side signals
- Using a single global ban list table without indexing `client_hash` and `composite_hash` — unindexed lookups on large ban tables will exceed D1 query time budgets
- Permanently blocking based on subnet alone — subnets are shared; use subnet hits only to increase risk score, not as a hard block signal

## Gotchas
- Canvas fingerprints are browser and GPU driver dependent; they will naturally drift when users upgrade their browser — weight canvas signals lower than ASN/timezone
- `req.cf` is a plain object in Cloudflare Workers; TypeScript types it as `unknown`, requiring a cast
- D1 `batch()` has a 100-statement limit per call — chunk large ban registration writes into batches of ≤ 100
- Turnstile `score` is only present for "managed" site keys; invisible keys return `success: true/false` without a score field

## Verification
1. Register an account, retrieve its `composite_hash` from `registration_fingerprints`, manually insert a `ban_fingerprints` row, then attempt a second registration with the same fingerprint — assert 403 response.
2. Rotate only the subnet signal and attempt re-registration — assert the client FP fuzzy match still triggers a 403.
3. Attempt registration with a bot-like Turnstile token (score < 0.5 from test keys) and assert the challenge rejection fires before fingerprint checks.
4. Call `topEvasionOffenders` and verify the query returns the seeded test offender in rank order.

## Related
- [`botnet-registration-detection-turnstile-fingerprinting.md`](botnet-registration-detection-turnstile-fingerprinting.md)
- [`repeat-offender-detection-anonymous-sessions.md`](repeat-offender-detection-anonymous-sessions.md)
- [`shadow-banning-reach-limiting-d1-workers.md`](shadow-banning-reach-limiting-d1-workers.md)
- [`account-suspension-appeals-worker-workflow.md`](account-suspension-appeals-worker-workflow.md)
- [`vpn-proxy-detection-geo-restrictions.md`](vpn-proxy-detection-geo-restrictions.md)

## Sources
- FingerprintJS device fingerprinting research blog (2024) — canvas and font entropy
- Cloudflare Turnstile developer documentation — score-based bot detection
- Electronic Frontier Foundation — Cover Your Tracks (Panopticlick) methodology
- D1 batch API documentation — Cloudflare Developers
