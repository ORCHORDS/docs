# Account Takeover Detection and Prevention

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Users report unauthorized access to their accounts: purchases they didn't make, profile edits they didn't initiate, or security emails they didn't request. Ops sees a spike in password-reset requests and support tickets for "someone hacked my account." Credential-stuffing bots run lists of breached email/password pairs against the login endpoint, achieving 0.5–3 % hit rates and compromising thousands of accounts before rate limits kick in.

Secondary signals: devices or IPs foreign to the account's historical footprint appearing in session logs, unusual access times, rapid sequential logins from geographically distant IPs (impossible travel), bulk item-redemption events, and changes to payment or 2FA methods shortly after login.

## Context

Account takeover (ATO) is the leading fraud vector for platforms with digital goods, subscriptions, or stored payment methods. The 2024 Verizon DBIR attributed 38 % of web-app breaches to stolen credentials. Modern ATO attacks use residential proxies to evade IP blocks, Puppeteer clusters to solve CAPTCHAs, and slow-drip credential stuffing (one attempt per account per hour) to stay under velocity thresholds.

Cloudflare Workers sits in front of every request. Turnstile provides bot scores. D1 holds session and account metadata. KV stores per-account risk signals with short TTLs. Workers AI (text classification) or an upstream risk API evaluates signals asynchronously. The goal is to intercept the ATO session before damage occurs—ideally at login—without adding friction for legitimate users.

Regulatory context: GDPR Article 32 requires appropriate technical measures; PCI-DSS 4.0 Requirement 8 mandates MFA for all access to cardholder data environments; NIST SP 800-63B governs authenticator assurance levels. Failing to detect ATO can trigger mandatory breach notifications under CCPA § 1798.150 and EU GDPR Article 33.

## Signal Collection and Fingerprinting

Collect device and behavioral signals at login time and bind them to a session fingerprint stored in KV.

```typescript
// workers/ato-signal-collector.ts
export interface LoginSignals {
  ip: string;
  asn: string;
  country: string;
  cfThreatScore: number;       // Cloudflare Bot Management score 0-100
  turnstileScore: number;      // Turnstile challenge outcome score
  userAgent: string;
  uaHash: string;              // SHA-256 of UA for compactness
  acceptLanguage: string;
  timezone: string;            // from JS Intl.DateTimeFormat if available
  screenRes: string;           // "1920x1080" from client JS
  cookiePresent: boolean;      // returning device has session cookie
  headerOrder: string;         // hash of HTTP header sequence (bot detection)
  timestamp: number;
}

export async function collectLoginSignals(
  request: Request,
  env: Env
): Promise<LoginSignals> {
  const cf = request.cf as CfProperties;
  const ip = request.headers.get("CF-Connecting-IP") ?? "";
  const ua = request.headers.get("User-Agent") ?? "";
  const uaHash = await hashString(ua);

  // Cloudflare Bot Management score (available on Enterprise / Bot Management add-on)
  const cfThreatScore = Number(request.headers.get("CF-Bot-Score") ?? cf.threatScore ?? 0);

  // Reconstruct header order fingerprint
  const headerNames: string[] = [];
  for (const [name] of request.headers) headerNames.push(name.toLowerCase());
  const headerOrder = await hashString(headerNames.join(","));

  return {
    ip,
    asn: String(cf.asn ?? ""),
    country: String(cf.country ?? ""),
    cfThreatScore,
    turnstileScore: 0, // filled after Turnstile verify
    userAgent: ua,
    uaHash,
    acceptLanguage: request.headers.get("Accept-Language") ?? "",
    timezone: "",      // filled from posted JSON body
    screenRes: "",     // filled from posted JSON body
    cookiePresent: request.headers.get("Cookie")?.includes("_sess=") ?? false,
    headerOrder,
    timestamp: Date.now(),
  };
}

async function hashString(s: string): Promise<string> {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16); // 8-byte prefix is sufficient for comparison
}
```

## Risk Scoring Engine

Combine signals into a risk score. Store per-account historical baselines in D1; compare against the incoming session.

```typescript
// workers/ato-risk-scorer.ts
import type { LoginSignals } from "./ato-signal-collector";

export interface RiskResult {
  score: number;          // 0–100, higher = more suspicious
  factors: string[];
  action: "allow" | "step_up" | "block";
}

export async function scoreLoginRisk(
  accountId: string,
  signals: LoginSignals,
  env: Env
): Promise<RiskResult> {
  const factors: string[] = [];
  let score = 0;

  // 1. Cloudflare threat / bot score
  if (signals.cfThreatScore > 50) { score += 30; factors.push("high_bot_score"); }
  else if (signals.cfThreatScore > 20) { score += 10; factors.push("elevated_bot_score"); }

  // 2. Impossible travel check — load last known country from KV
  const lastCountryKey = `ato:country:${accountId}`;
  const lastCountry = await env.KV.get(lastCountryKey);
  if (lastCountry && lastCountry !== signals.country) {
    score += 25;
    factors.push(`impossible_travel:${lastCountry}->${signals.country}`);
  }

  // 3. New device fingerprint
  const knownDevicesKey = `ato:devices:${accountId}`;
  const knownDevicesRaw = await env.KV.get(knownDevicesKey);
  const knownDevices: string[] = knownDevicesRaw ? JSON.parse(knownDevicesRaw) : [];
  const deviceFp = `${signals.uaHash}:${signals.headerOrder}`;
  if (!knownDevices.includes(deviceFp)) {
    score += 20;
    factors.push("new_device_fingerprint");
  }

  // 4. No session cookie on account that has logged in before
  const loginCountKey = `ato:logins:${accountId}`;
  const loginCount = Number(await env.KV.get(loginCountKey) ?? "0");
  if (loginCount > 3 && !signals.cookiePresent) {
    score += 15;
    factors.push("missing_cookie_returning_account");
  }

  // 5. High-risk ASN (Tor exits, known proxy ranges via D1 blocklist)
  const isBadAsn = await env.DB.prepare(
    "SELECT 1 FROM bad_asns WHERE asn = ? LIMIT 1"
  ).bind(signals.asn).first<{ 1: number }>();
  if (isBadAsn) { score += 25; factors.push("bad_asn"); }

  // Clamp and decide
  score = Math.min(score, 100);
  const action: RiskResult["action"] =
    score >= 70 ? "block" : score >= 35 ? "step_up" : "allow";

  // Update rolling state (fire-and-forget — do not await on critical path)
  env.ctx.waitUntil(updateAccountBaseline(accountId, signals, env));

  return { score, factors, action };
}

async function updateAccountBaseline(
  accountId: string,
  signals: LoginSignals,
  env: Env
): Promise<void> {
  const ttl = 90 * 24 * 3600; // 90 days

  // Update last country
  await env.KV.put(`ato:country:${accountId}`, signals.country, { expirationTtl: ttl });

  // Append device fingerprint (cap list at 10 known devices)
  const raw = await env.KV.get(`ato:devices:${accountId}`);
  const devices: string[] = raw ? JSON.parse(raw) : [];
  const fp = `${signals.uaHash}:${signals.headerOrder}`;
  if (!devices.includes(fp)) {
    devices.push(fp);
    if (devices.length > 10) devices.shift();
    await env.KV.put(`ato:devices:${accountId}`, JSON.stringify(devices), { expirationTtl: ttl });
  }

  // Increment login counter
  const count = Number(await env.KV.get(`ato:logins:${accountId}`) ?? "0");
  await env.KV.put(`ato:logins:${accountId}`, String(count + 1), { expirationTtl: ttl });
}
```

## Step-Up Authentication and Session Invalidation

When `action === "step_up"`, require email OTP before completing login. When `action === "block"`, log and reject.

```typescript
// workers/ato-enforcement.ts
import { scoreLoginRisk } from "./ato-risk-scorer";
import { collectLoginSignals } from "./ato-signal-collector";

export async function handleLogin(request: Request, env: Env): Promise<Response> {
  const body = await request.json<{ email: string; password: string; timezone?: string; screen?: string }>();
  const signals = await collectLoginSignals(request, env);
  signals.timezone = body.timezone ?? "";
  signals.screenRes = body.screen ?? "";

  // Authenticate credentials first (argon2 verify via DO or upstream service)
  const account = await verifyCredentials(body.email, body.password, env);
  if (!account) {
    // Record failed attempt — useful for brute-force detection
    await env.KV.put(
      `ato:fail:${signals.ip}`,
      String(Number(await env.KV.get(`ato:fail:${signals.ip}`) ?? "0") + 1),
      { expirationTtl: 900 }
    );
    return Response.json({ error: "invalid_credentials" }, { status: 401 });
  }

  const risk = await scoreLoginRisk(account.id, signals, env);

  if (risk.action === "block") {
    // Log to D1 for audit
    await env.DB.prepare(
      "INSERT INTO ato_events (account_id, ip, score, factors, action, ts) VALUES (?,?,?,?,?,?)"
    ).bind(account.id, signals.ip, risk.score, JSON.stringify(risk.factors), "block", Date.now()).run();

    return Response.json({ error: "access_denied", code: "ATO_BLOCK" }, { status: 403 });
  }

  if (risk.action === "step_up") {
    const otpToken = await issueEmailOtp(account.email, env);
    return Response.json({ status: "step_up_required", otp_token: otpToken }, { status: 202 });
  }

  // Low risk — issue session
  const session = await createSession(account.id, signals, env);
  return Response.json({ session_token: session.token });
}

// Invalidate all sessions for an account (used on ATO confirmed)
export async function invalidateAllSessions(accountId: string, env: Env): Promise<void> {
  await env.DB.prepare(
    "UPDATE sessions SET revoked = 1, revoked_reason = 'ato_confirmed' WHERE account_id = ? AND revoked = 0"
  ).bind(accountId).run();

  // Clear device and country baselines so next login requires fresh verification
  await Promise.all([
    env.KV.delete(`ato:country:${accountId}`),
    env.KV.delete(`ato:devices:${accountId}`),
  ]);
}

declare function verifyCredentials(email: string, password: string, env: Env): Promise<{ id: string; email: string } | null>;
declare function issueEmailOtp(email: string, env: Env): Promise<string>;
declare function createSession(accountId: string, signals: LoginSignals, env: Env): Promise<{ token: string }>;
import type { LoginSignals } from "./ato-signal-collector";
```

## Post-Login Continuous Monitoring

ATO does not always happen at login time — session tokens can be stolen. Add a middleware that re-validates session context on sensitive actions (checkout, password change, 2FA update).

```typescript
// workers/ato-session-guard.ts
const SENSITIVE_PATHS = new Set([
  "/api/account/password",
  "/api/account/email",
  "/api/account/mfa",
  "/api/payments/checkout",
  "/api/payments/refund",
]);

export async function sessionGuardMiddleware(
  request: Request,
  env: Env,
  next: () => Promise<Response>
): Promise<Response> {
  const url = new URL(request.url);
  if (!SENSITIVE_PATHS.has(url.pathname)) return next();

  const sessionToken = request.headers.get("Authorization")?.replace("Bearer ", "");
  if (!sessionToken) return Response.json({ error: "unauthenticated" }, { status: 401 });

  const session = await env.DB.prepare(
    "SELECT account_id, created_ip, created_country, revoked FROM sessions WHERE token = ?"
  ).bind(sessionToken).first<{ account_id: string; created_ip: string; created_country: string; revoked: number }>();

  if (!session || session.revoked) {
    return Response.json({ error: "session_invalid" }, { status: 401 });
  }

  // Country anomaly on sensitive action
  const cf = (request as any).cf as CfProperties;
  const currentCountry = String(cf?.country ?? "");
  if (currentCountry && session.created_country && currentCountry !== session.created_country) {
    // Force re-authentication
    await env.DB.prepare(
      "UPDATE sessions SET revoked = 1, revoked_reason = 'country_mismatch_sensitive_action' WHERE token = ?"
    ).bind(sessionToken).run();
    return Response.json({ error: "session_invalidated", reason: "country_change" }, { status: 401 });
  }

  return next();
}
```

## Anti-patterns

- **Blocking on IP alone** — residential proxy networks recycle IPs constantly; IP blocks hurt legitimate users in shared networks (corporate NAT, mobile carriers) and don't stop determined attackers.
- **Waiting for chargebacks to detect ATO** — by the time a chargeback lands, the attacker has liquidated the account. Risk scoring must fire at login.
- **Storing raw failed-attempt counts in KV without TTL** — a counter that never expires will permanently ban users who legitimately forget passwords.
- **Treating step-up as a hard gate for all anomalies** — returning users on a new device (new laptop, travel) will be step-up'd constantly. Calibrate thresholds with real false-positive data.
- **Skipping session invalidation on confirmed ATO** — if only the current session is killed, the attacker may have cloned the token to another location and keeps access.
- **Using predictable OTP lengths or delivery delays** — 4-digit OTPs have only 10,000 combinations; use 6-digit codes with 5-minute TTLs and rate-limit OTP attempts separately.

## Gotchas

- `request.cf.threatScore` is always `0` on the free tier; you need Bot Management (Enterprise) or Turnstile for a meaningful score.
- `CF-Bot-Score` header is only present when Cloudflare Bot Management is enabled for the zone — fall back gracefully to `0`.
- KV TTL is set in seconds (integer), not milliseconds. Passing `Date.now()` (milliseconds) as `expirationTtl` will silently cause the key to expire almost immediately or be rejected.
- Impossible-travel checks produce false positives for VPN users. Supplement with ASN reputation rather than relying solely on country codes.
- D1 `first()` returns `null` when no row matches, not an empty object — always null-check before reading properties.
- `waitUntil` budget on Workers is 30 seconds after the response is returned. If baseline updates take longer (D1 under load), they will be cut off — keep them fast.
- Email OTP delivery latency (SES, Postmark) can reach 30+ seconds on busy queues; user-facing error messages should set expectations and offer SMS fallback.

## Verification

```bash
# 1. Simulate credential-stuffing: correct password, new country in CF header
curl -X POST https://api.example.com/auth/login \
  -H "CF-Connecting-IP: 5.5.5.5" \
  -H "CF-IPCountry: RU" \
  -H "CF-Bot-Score: 75" \
  -d '{"email":"test@example.com","password":"correct"}'
# Expect: {"error":"access_denied","code":"ATO_BLOCK"} or step_up_required

# 2. Verify D1 audit log recorded the event
wrangler d1 execute DB --command \
  "SELECT * FROM ato_events WHERE account_id='...' ORDER BY ts DESC LIMIT 5"

# 3. Verify KV state cleared after confirmed ATO
wrangler kv key get --binding=KV "ato:country:<accountId>"
# Expect: (empty / null)

# 4. Load test the scoring path — must not add > 20 ms p99 latency to login
npx artillery run ato-load-test.yml

# 5. Check session invalidation
curl -X GET https://api.example.com/api/account/profile \
  -H "Authorization: Bearer <revoked_token>"
# Expect: 401 session_invalid
```

## Related

- `botnet-registration-detection-turnstile-fingerprinting.md` — bot detection at signup
- `repeat-offender-detection-anonymous-sessions.md` — session-level abuse recidivism
- `rate-limit-abuse-tor-exit-node-detection.md` — IP-layer threat blocking
- `anonymous-platform-abuse-prevention.md` — layered abuse defense
- `platform-trust-score-cloudflare-signals.md` — aggregate risk scoring

## Sources

- NIST SP 800-63B Digital Identity Guidelines (2024 revision)
- Cloudflare Bot Management documentation — `developers.cloudflare.com/bots`
- Verizon Data Breach Investigations Report 2024
- OWASP Credential Stuffing Prevention Cheat Sheet — `cheatsheetseries.owasp.org`
- PCI DSS v4.0 Requirement 8 — Strong Authentication
- Turnstile developer documentation — `developers.cloudflare.com/turnstile`
