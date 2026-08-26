# VPN/Proxy Detection for Geographic Content Restrictions
- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

example project (example.com) is age-gated to 21+ users and must enforce jurisdiction-specific content restrictions —
some content categories (explicit material, gambling-adjacent features, Solana wagering) are illegal or
require additional licensing in certain regions. Users who connect through VPNs, residential proxies, or
Tor exit nodes can bypass geo-enforcement, circumvent age-verification flows tied to local regulators, and
access features the platform cannot legally serve to their true jurisdiction.

Cloudflare Workers intercepts every request and exposes `cf.country` on the incoming request object, but
this value reflects the exit-node country, not the user's physical location, when a VPN is in use. Operators
need a layered signal stack that flags likely tunnel users without erroneously blocking legitimate anonymous
browsing that is not jurisdiction-hopping.

---

## Context

example project runs entirely on Cloudflare Workers + D1 + R2. There is no traditional server fleet.
Anonymous sessions are keyed by a short-lived session token that carries no PII; the only persistent
identifiers available are Cloudflare's bot-management signals and optional wallet-linked attestations
(Solana public key or zk-age proof). Geo-blocking must therefore be session-level, not account-level.

Key regulatory pressure points:
- **UK Online Safety Act 2023 / 2026 enforcement window**: requires age assurance *and* jurisdictional
  content gating for platforms accessible from the UK.
- **EU DSA Article 28**: platforms must not serve certain categories to minors regardless of VPN state.
- **US state laws (CA AB 2273, TX HB 1709, LA HB 142)**: mandate age verification; VPN bypass
  directly violates the operator's compliance posture with those regulators.
- **MiCA Art. 76**: crypto-adjacent features face additional geo-licensing requirements (EEA passporting
  vs. third-country restrictions).

---

## Section 1 — Signal Layers

Cloudflare exposes five proxy/VPN signals on the `cf` object with no extra billing:

| Field                        | What it tells you                                      | Reliability |
|------------------------------|--------------------------------------------------------|-------------|
| `cf.isEUCountry`             | Determined by Cloudflare routing, not client headers   | High        |
| `cf.botManagement.score`     | 1–99; low score = likely automated / tunnel            | Medium-High |
| `cf.botManagement.verifiedBot` | Cloudflare-verified crawler whitelist                | High        |
| `cf.ipThreatScore`           | Aggregate threat reputation of the IP                  | Medium      |
| `cf.asn` / `cf.asOrganization` | ASN of the connecting IP                             | High        |

Commercial VPN providers (NordVPN, ExpressVPN, Mullvad) operate from well-known ASN ranges.
Cloudflare Workers AI's IP-intelligence product (`workers-ai/ip-intelligence-v1`) is an additional
paid signal that returns `proxy`, `vpn`, `tor`, `hosting`, or `residential` labels per IP.

Residential proxy networks are the hardest to detect: they route through real home ISP connections,
so `cf.ipThreatScore` is low and the ASN looks clean. Behavioral fingerprinting (request cadence,
TLS fingerprint via JA4, timezone vs. claimed country) is required for high-assurance enforcement.

---

## Section 2 — D1 Schema

```sql
-- geo_enforcement
CREATE TABLE IF NOT EXISTS geo_enforcement (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  session_token TEXT    NOT NULL,
  detected_asn  INTEGER,
  cf_country    TEXT    NOT NULL,
  ip_label      TEXT,           -- vpn | tor | hosting | residential | clean
  bot_score     INTEGER,
  threat_score  INTEGER,
  tz_drift_ms   INTEGER,        -- client TZ vs. CF country TZ offset
  action        TEXT    NOT NULL DEFAULT 'allow', -- allow | restrict | block | challenge
  restricted_features TEXT,     -- JSON array of features withheld
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS geo_enforcement_session
  ON geo_enforcement (session_token, created_at DESC);

-- known_vpn_asns  (updated via scheduled cron Worker)
CREATE TABLE IF NOT EXISTS known_vpn_asns (
  asn           INTEGER PRIMARY KEY,
  label         TEXT NOT NULL,  -- vpn | datacenter | tor
  confidence    TEXT NOT NULL DEFAULT 'medium', -- low | medium | high
  updated_at    INTEGER NOT NULL DEFAULT (unixepoch())
);
```

---

## Section 3 — Worker Implementation

```typescript
// geo-enforcement.ts  (runs as middleware in the example project request pipeline)

interface Env {
  DB: D1Database;
  SESSION_KV: KVNamespace;
  AI: Ai;
}

const RESTRICTED_FEATURES_BY_COUNTRY: Record<string, string[]> = {
  US: [],       // baseline — state-level handled at checkout
  CN: ['explicit_media', 'crypto_wagering', 'solana_features'],
  RU: ['crypto_wagering', 'solana_features'],
  KP: ['*'],    // total block
  IR: ['*'],
  SY: ['*'],
};

const BLOCKED_COUNTRIES = new Set(['KP', 'IR', 'SY', 'CU', 'SD']);

export async function geoEnforcementMiddleware(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<{ action: string; restrictedFeatures: string[]; reason: string }> {
  const cf = request.cf as CfProperties & {
    asn?: number;
    asOrganization?: string;
    botManagement?: { score: number; verifiedBot: boolean };
    ipThreatScore?: number;
  };

  const country = cf.country ?? 'XX';
  const asn = cf.asn ?? 0;
  const botScore = cf.botManagement?.score ?? 99;
  const threatScore = cf.ipThreatScore ?? 0;

  // --- Fast path: OFAC/sanctions hard block ---
  if (BLOCKED_COUNTRIES.has(country)) {
    return { action: 'block', restrictedFeatures: ['*'], reason: 'ofac_sanctions' };
  }

  // --- ASN check against known VPN/datacenter ranges ---
  const asnRow = await env.DB.prepare(
    'SELECT label, confidence FROM known_vpn_asns WHERE asn = ?'
  ).bind(asn).first<{ label: string; confidence: string }>();

  let ipLabel = 'clean';
  let action = 'allow';
  let reason = 'clean';

  if (asnRow) {
    ipLabel = asnRow.label;
    if (asnRow.label === 'tor') {
      action = 'block';
      reason = 'tor_exit_node';
    } else if (asnRow.label === 'vpn' && asnRow.confidence === 'high') {
      action = 'challenge'; // Cloudflare Turnstile interstitial
      reason = 'known_vpn_asn';
    }
  }

  // --- Bot score heuristic ---
  if (botScore < 15 && !cf.botManagement?.verifiedBot) {
    action = action === 'allow' ? 'challenge' : action;
    reason = reason === 'clean' ? 'low_bot_score' : reason;
  }

  // --- Timezone drift check (requires client to send Intl.DateTimeFormat locale) ---
  const clientTz = request.headers.get('X-Client-Timezone') ?? null;
  let tzDriftMs = 0;
  if (clientTz) {
    tzDriftMs = computeTzDrift(country, clientTz);
    if (Math.abs(tzDriftMs) > 3 * 60 * 60 * 1000) {
      // >3h difference between claimed country and reported TZ
      ipLabel = ipLabel === 'clean' ? 'suspicious_tz' : ipLabel;
      action = action === 'allow' ? 'restrict' : action;
      reason = reason === 'clean' ? 'timezone_mismatch' : reason;
    }
  }

  // Determine feature restrictions based on resolved country
  const restrictedFeatures = RESTRICTED_FEATURES_BY_COUNTRY[country] ?? [];

  // Persist enforcement decision (fire-and-forget)
  const sessionToken = request.headers.get('X-Session-Token') ?? 'anon';
  ctx.waitUntil(
    env.DB.prepare(`
      INSERT INTO geo_enforcement
        (session_token, detected_asn, cf_country, ip_label, bot_score, threat_score, tz_drift_ms, action, restricted_features)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      sessionToken, asn, country, ipLabel, botScore, threatScore, tzDriftMs,
      action, JSON.stringify(restrictedFeatures)
    ).run()
  );

  return { action, restrictedFeatures, reason };
}

function computeTzDrift(cfCountry: string, clientTz: string): number {
  // Map CF country to expected UTC offset(s); use midpoint if multiple zones.
  // Returns ms of absolute offset between expected and actual.
  const COUNTRY_UTC_OFFSET_MS: Record<string, number> = {
    US: -5 * 3600000,  // approximate EST/CST median
    GB: 0,
    DE: 1 * 3600000,
    JP: 9 * 3600000,
    // ... extend per coverage needs
  };
  try {
    const now = Date.now();
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone: clientTz,
      timeZoneName: 'shortOffset',
    });
    const parts = formatter.formatToParts(new Date(now));
    const offsetStr = parts.find(p => p.type === 'timeZoneName')?.value ?? 'GMT+0';
    const match = offsetStr.match(/GMT([+-]\d+)/);
    const clientOffsetMs = match ? parseInt(match[1], 10) * 3600000 : 0;
    const expectedOffsetMs = COUNTRY_UTC_OFFSET_MS[cfCountry] ?? 0;
    return clientOffsetMs - expectedOffsetMs;
  } catch {
    return 0;
  }
}
```

---

## Section 4 — Scheduled ASN List Refresh

```typescript
// cron-vpn-asn-refresh.ts  (scheduled Worker, runs daily)
// Pulls RIPE/BGP data + commercial blocklist to refresh known_vpn_asns

export default {
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    // Use a static list augmented by a commercial IP-intelligence API
    const response = await fetch('https://raw.githubusercontent.com/X4BNet/lists_vpn/main/ipv4.txt');
    if (!response.ok) return;

    const text = await response.text();
    const cidrs = text.split('\n').filter(l => l.trim() && !l.startsWith('#'));

    // For each CIDR, resolve ASN via BGP data (simplified: use Cloudflare's WHOIS endpoint)
    // In production: batch-resolve CIDRs → ASNs and upsert known_vpn_asns
    // This snippet shows the upsert pattern only:

    const batch: D1PreparedStatement[] = [];
    const exampleAsns = [{ asn: 9009, label: 'vpn', confidence: 'high' }]; // placeholder

    for (const { asn, label, confidence } of exampleAsns) {
      batch.push(
        env.DB.prepare(`
          INSERT INTO known_vpn_asns (asn, label, confidence, updated_at)
          VALUES (?, ?, ?, unixepoch())
          ON CONFLICT(asn) DO UPDATE SET label=excluded.label,
            confidence=excluded.confidence, updated_at=unixepoch()
        `).bind(asn, label, confidence)
      );
    }
    await env.DB.batch(batch);
  }
};
```

---

## Anti-patterns

- **Blocking all datacenter IPs**: Legitimate users (developers, CI bots checking example project API) connect
  from cloud IPs. Use `challenge` not `block` for ambiguous ASNs; reserve hard `block` for Tor and
  OFAC-listed countries.
- **Trusting `X-Forwarded-For` headers**: These are trivially spoofed. Always use `request.cf.country`
  which Cloudflare populates from the actual edge connection IP, not the header chain.
- **Single-signal decisions**: One signal (e.g., bot score < 20) produces too many false positives.
  Require at least two corroborating signals before restricting features.
- **Storing raw IPs in D1**: GDPR Article 4(1) classifies IP addresses as personal data. Store ASN and
  CF country only; never log the raw client IP in D1 or R2 access logs.
- **Permanent geo-blocks without appeal**: UK OSA §14 and EU DSA §17 give users a right to contest
  automated decisions. Surface a `Contact Support` path even when blocking.

---

## Gotchas

- `cf.country` returns `'T1'` for Tor circuits — this is a Cloudflare-specific pseudo-code, not an
  ISO 3166-1 alpha-2 country. Add `T1` to your `BLOCKED_COUNTRIES` set.
- `cf.botManagement` is only populated when Bot Management is purchased. The free-tier `cf.isEU`
  and `cf.country` fields are always present.
- Workers AI `ip-intelligence-v1` has a 200ms P95 latency — run it in `ctx.waitUntil` after the
  enforcement decision rather than on the critical path.
- Cloudflare's edge pops return `cf.country = 'XX'` for private ranges (10.x, 172.16.x, 192.168.x)
  when testing locally with `wrangler dev`. Handle the `'XX'` case explicitly.
- Solana wallet signatures (used in example project's optional de-anonymization flow) do not prove
  jurisdiction — a US-sanctioned person can hold a Solana wallet. Geo enforcement must remain
  IP-layer regardless of wallet attestation.

---

## Verification

```bash
# 1. Verify Tor exit node is blocked (T1 pseudo-code)
curl -H "CF-IPCountry: T1" https://example.com/api/session/init
# Expected: 403 with reason="ofac_sanctions" or "tor_exit_node"

# 2. Verify OFAC country block
curl -H "CF-IPCountry: IR" https://example.com/api/session/init
# Expected: 403

# 3. Verify VPN challenge (requires known VPN ASN in D1)
# Insert test row: INSERT INTO known_vpn_asns VALUES (9009,'vpn','high',unixepoch())
# Connect via an IP in ASN 9009, expect 429/challenge response

# 4. Verify D1 enforcement log
wrangler d1 execute example project-prod --command \
  "SELECT action, reason, COUNT(*) FROM geo_enforcement
   WHERE created_at > unixepoch() - 3600 GROUP BY action, reason;"

# 5. Verify feature restriction payload
curl https://example.com/api/features \
  -H "CF-IPCountry: CN" -H "X-Session-Token: test123"
# Expected JSON: { "restricted": ["explicit_media","crypto_wagering","solana_features"] }
```

---

## Related

- `rate-limit-abuse-tor-exit-node-detection.md`
- `platform-trust-score-cloudflare-signals.md`
- `age-verification-cloudflare-workers-kyc.md`
- `cryptocurrency-regulatory-risk-platform.md`
- `user-privacy-law-enforcement-requests.md`
- `digital-services-act-platform-compliance.md`

---

## Sources

- Cloudflare Workers `request.cf` reference — https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- Cloudflare Bot Management — https://developers.cloudflare.com/bots/plans/bm-subscription/
- OFAC SDN/blocked-countries list — https://ofac.treasury.gov/sanctions-programs-and-country-information
- X4BNet VPN IP lists (BGP-derived) — https://github.com/X4BNet/lists_vpn
- UK Online Safety Act 2023 §14 (automated decisions + appeal) — https://www.legislation.gov.uk/ukpga/2023/50
- MiCA Regulation (EU) 2023/1114, Art. 76 — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1114
