# SafeMessaging Compliance: Responding to Self-Harm Content Per AFSP/reportingonsuicide.org Guidelines

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

example project detects a post containing suicidal ideation (via Workers AI classifier). The detection fires correctly, but the *response* — what the user sees, what data is logged, and how crisis resources are surfaced — must comply with the SafeMessaging guidelines from AFSP and reportingonsuicide.org. Shipping the wrong copy, the wrong resource link, or logging too much detail can itself constitute harm and expose the platform to regulatory risk.

## Context

SafeMessaging is not about detection; it is about **how you communicate** once detection fires. Core rules:
- Do not describe method, location, or circumstances of past attempts.
- Do not use the phrase "committed suicide" — use "died by suicide".
- Surface the 988 Suicide & Crisis Lifeline (US), Crisis Text Line, and locale-appropriate equivalents.
- Intervening copy must not be alarmist or stigmatising.
- Internally, suppress method/detail fields from analytics pipelines to prevent normalisation.

Non-compliance risk: DSA Art. 28, UK Online Safety Act, Australian Online Safety Act all require demonstrable "crisis safety" measures. Auditors check copy and log schemas, not just detection rates.

## 1. SafeMessaging Copy Constants in Workers KV

Store regulated copy in KV so it can be updated without code deployment:

```typescript
// scripts/seed-safemessaging-kv.ts
const SAFE_COPY: Record<string, string> = {
  "intervention_headline_en": "It looks like you might be going through something difficult.",
  "intervention_body_en": "You are not alone. Free, confidential support is available 24/7.",
  "cta_us": "Call or text 988 (Suicide & Crisis Lifeline)",
  "cta_uk": "Call 116 123 (Samaritans)",
  "cta_au": "Call 13 11 14 (Lifeline Australia)",
  "cta_global": "Visit findahelpline.com for local crisis services",
};

// Seed via wrangler:
// wrangler kv:key put --namespace-id=$KV_ID "intervention_headline_en" "..."
```

## 2. Response Interception Worker

```typescript
// src/safemessaging-gate.ts
import type { Env } from "./types";

export async function applySafeMessagingInterstitial(
  postText: string,
  userLocale: string,
  env: Env
): Promise<{ blocked: boolean; interstitial?: SafeMessagingPayload }> {

  const score = await classifySelfHarm(postText, env);
  if (score < 0.75) return { blocked: false };

  const locale = userLocale.startsWith("en-GB") ? "uk"
    : userLocale.startsWith("en-AU") ? "au"
    : userLocale.startsWith("en") ? "us"
    : "global";

  const [headline, body, cta] = await Promise.all([
    env.KV_COPY.get(`intervention_headline_en`),
    env.KV_COPY.get(`intervention_body_en`),
    env.KV_COPY.get(`cta_${locale}`),
  ]);

  return {
    blocked: true,
    interstitial: {
      headline: headline ?? "You are not alone.",
      body: body ?? "",
      cta: cta ?? "Visit findahelpline.com",
      score,          // internal only — never send to client
    },
  };
}
```

## 3. Method-Detail Suppression in D1 Log Schema

```sql
-- migration: 0042_safemessaging_log_suppression.sql
CREATE TABLE self_harm_events (
  id          TEXT PRIMARY KEY,
  session_id  TEXT NOT NULL,
  detected_at INTEGER NOT NULL,
  score       REAL NOT NULL,
  locale      TEXT NOT NULL,
  -- method_detail column intentionally omitted per SafeMessaging §3.2
  -- do NOT add free-text content columns here
  interstitial_shown INTEGER NOT NULL DEFAULT 0,
  cta_clicked        INTEGER NOT NULL DEFAULT 0,
  post_suppressed    INTEGER NOT NULL DEFAULT 0
);
```

```typescript
// src/safemessaging-log.ts
export async function logSafeMessagingEvent(
  env: Env,
  sessionId: string,
  score: number,
  locale: string,
  ctaClicked: boolean
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO self_harm_events
       (id, session_id, detected_at, score, locale, interstitial_shown, cta_clicked)
     VALUES (?, ?, ?, ?, ?, 1, ?)`
  ).bind(crypto.randomUUID(), sessionId, Date.now(), score, locale, ctaClicked ? 1 : 0).run();
}
```

## 4. Locale-Aware CTA Routing

```typescript
// src/crisis-router.ts
const CTA_MAP: Record<string, { label: string; href: string }> = {
  us:     { label: "Call or text 988", href: "tel:988" },
  uk:     { label: "Call 116 123 (Samaritans)", href: "tel:116123" },
  au:     { label: "Call 13 11 14 (Lifeline)", href: "tel:131114" },
  ca:     { label: "Call 1-833-456-4566", href: "tel:18334564566" },
  global: { label: "Find local help", href: "https://findahelpline.com" },
};

export function getCrisisCTA(locale: string): { label: string; href: string } {
  const country = locale.split("-")[1]?.toLowerCase() ?? "global";
  return CTA_MAP[country] ?? CTA_MAP["global"];
}
```

## 5. Audit Log for Compliance Reporting

```typescript
// src/safemessaging-audit.ts
export async function auditSafeMessagingCompliance(env: Env): Promise<ComplianceReport> {
  const { results } = await env.DB.prepare(
    `SELECT
       COUNT(*) AS total_events,
       SUM(interstitial_shown) AS interstitials_shown,
       SUM(cta_clicked) AS ctas_clicked,
       AVG(score) AS avg_score,
       locale
     FROM self_harm_events
     WHERE detected_at > ?
     GROUP BY locale`
  ).bind(Date.now() - 30 * 86400 * 1000).all();

  return {
    period: "30d",
    byLocale: results as LocaleBreakdown[],
    // Never include post content or method details in this report
  };
}
```

## Anti-patterns

- **Logging post content** in self_harm_events — violates SafeMessaging §3.2 and GDPR minimisation.
- **Using "committed suicide"** in any copy string, even draft copy in KV.
- **Showing score to user** — the confidence score is operational data, not end-user data.
- **Blocking without interstitial** — silent suppression without surfacing resources is non-compliant with UK OSA s.12.
- **One global CTA** — 988 is US-only; non-US users seeing a US number erodes trust and utility.

## Gotchas

- KV reads in Cloudflare Workers are eventually consistent — seed copy changes at least 60 s before expecting them in all edge PoPs.
- `score` must not appear in Analytics Engine dimensions (only metrics) to avoid user-identifiable profiling.
- The 988 number became active July 2022; older runbooks may reference 1-800-273-8255 — audit all copy annually.
- DSA Art. 28 requires documented evidence of crisis measures; keep the `self_harm_events` aggregate query as a named view for auditor access.

## Verification

```bash
# Check KV copy seed
wrangler kv:key list --namespace-id=$KV_COPY_ID | jq '.[].name'

# Confirm no content columns in schema
wrangler d1 execute example project-db --command \
  "PRAGMA table_info(self_harm_events);" | grep -i "content\|text\|method"
# Expected: no rows

# Spot-check CTA routing
curl -s https://example project.example.com/api/debug/crisis-cta?locale=en-AU \
  | jq '.href'
# Expected: "tel:131114"
```

## Related

- `self-harm-content-detection-workers-ai.md`
- `crisis-intervention-detection-workers-ai.md`
- `doxxing-pii-scan-prevention-workers-ai.md`
- `platform-health-score-dashboard-analytics-engine.md`

## Sources

- AFSP SafeMessaging Guidelines v4 — https://afsp.org/suicide-reporting
- reportingonsuicide.org Recommendations 2023
- UK Online Safety Act 2023, s.12 (Safety duties)
- DSA Article 28 — Protection of minors
- 988 Suicide & Crisis Lifeline — https://988lifeline.org
- findahelpline.com — global directory
