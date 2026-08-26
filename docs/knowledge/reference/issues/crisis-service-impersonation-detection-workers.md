# Crisis Service Impersonation Detection — Workers & D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Users report that accounts on example project are impersonating crisis hotlines (e.g., 988 Suicide & Crisis Lifeline), domestic violence shelters, emergency helplines, or official mental health services. Victims in distress contact these fake accounts and receive harmful or misleading advice, or are directed to off-platform contacts. This is distinct from brand impersonation (covered elsewhere) because the harm vector is acute — a person in crisis seeking real help is re-directed to an actor with potentially malicious intent.

## Context

Crisis-service impersonation exploits the anonymity and low-friction account creation of example project Impersonators copy official account handles, display names, and bios verbatim or with minor typos. They may use official logos as avatars. The risk is not just regulatory (FTC, DSA) but immediate physical safety. Detection must be fast (< 500 ms inline) to prevent even initial contact routing. The stack is: D1 (canonical crisis service registry), Workers AI (fuzzy name matching + bio similarity), KV (hot-path cache), and R2 (evidence snapshots for law enforcement escalation).

## 1. Canonical Crisis Service Registry

```sql
-- migrations/0062_crisis_registry.sql
CREATE TABLE IF NOT EXISTS crisis_services (
  id              TEXT PRIMARY KEY,
  canonical_name  TEXT NOT NULL,    -- e.g. "988 Suicide & Crisis Lifeline"
  handle_variants TEXT NOT NULL,    -- JSON array of known official handles
  country_code    TEXT NOT NULL,
  phone           TEXT,
  website         TEXT,
  logo_phash      TEXT,             -- perceptual hash of official logo
  added_at        INTEGER NOT NULL,
  source          TEXT NOT NULL     -- e.g. "SAMHSA", "NCADV", "Samaritans"
);

CREATE TABLE IF NOT EXISTS crisis_impersonation_reports (
  report_id   TEXT PRIMARY KEY,
  account_id  TEXT NOT NULL,
  service_id  TEXT NOT NULL REFERENCES crisis_services(id),
  score       REAL NOT NULL,        -- 0..1 confidence
  signals     TEXT NOT NULL,        -- JSON: which signals triggered
  detected_at INTEGER NOT NULL,
  action      TEXT                  -- suspended | escalated | false_positive
);
```

## 2. Handle Fuzzy Match (Inline Worker Check)

```typescript
// src/crisis-handle-check.ts
function editDistance(a: string, b: string): number {
  const dp: number[][] = Array.from({ length: a.length + 1 }, (_, i) =>
    Array.from({ length: b.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= a.length; i++)
    for (let j = 1; j <= b.length; j++)
      dp[i][j] =
        a[i - 1] === b[j - 1]
          ? dp[i - 1][j - 1]
          : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
  return dp[a.length][b.length];
}

export async function checkHandleForCrisisImpersonation(
  candidateHandle: string,
  env: Env
): Promise<{ match: boolean; serviceId: string | null; distance: number }> {
  const cacheKey = `crisis:handles:v1`;
  let variants: Array<{ handle: string; service_id: string }> = [];

  const cached = await env.KV.get(cacheKey, "json");
  if (cached) {
    variants = cached as typeof variants;
  } else {
    const rows = await env.DB.prepare(
      "SELECT id as service_id, handle_variants FROM crisis_services"
    ).all<{ service_id: string; handle_variants: string }>();

    for (const { service_id, handle_variants } of rows.results) {
      const parsed: string[] = JSON.parse(handle_variants);
      for (const h of parsed) variants.push({ handle: h.toLowerCase(), service_id });
    }
    await env.KV.put(cacheKey, JSON.stringify(variants), { expirationTtl: 600 });
  }

  const candidate = candidateHandle.toLowerCase().replace(/[^a-z0-9]/g, "");
  let bestDistance = Infinity;
  let bestServiceId: string | null = null;

  for (const { handle, service_id } of variants) {
    const normalized = handle.replace(/[^a-z0-9]/g, "");
    const d = editDistance(candidate, normalized);
    if (d < bestDistance) {
      bestDistance = d;
      bestServiceId = service_id;
    }
  }

  // Distance <= 2 on a handle ≥ 6 chars is considered a match
  const isMatch = bestDistance <= 2 && candidate.length >= 6;
  return { match: isMatch, serviceId: isMatch ? bestServiceId : null, distance: bestDistance };
}
```

## 3. Bio Semantic Similarity (Workers AI)

```typescript
// src/crisis-bio-check.ts
export async function scoreBioSimilarity(
  candidateBio: string,
  serviceId: string,
  env: Env
): Promise<number> {
  const service = await env.DB.prepare(
    "SELECT canonical_name, phone, website FROM crisis_services WHERE id = ?"
  )
    .bind(serviceId)
    .first<{ canonical_name: string; phone: string; website: string }>();

  if (!service) return 0;

  const referenceBio = `${service.canonical_name}. Call ${service.phone}. Visit ${service.website}`;

  const [candidateEmbed, referenceEmbed] = await Promise.all([
    env.AI.run("@cf/baai/bge-large-en-v1.5", { text: [candidateBio] }),
    env.AI.run("@cf/baai/bge-large-en-v1.5", { text: [referenceBio] }),
  ]);

  const cv = candidateEmbed.data[0] as number[];
  const rv = referenceEmbed.data[0] as number[];
  const dot = cv.reduce((s, v, i) => s + v * rv[i], 0);
  const normC = Math.sqrt(cv.reduce((s, v) => s + v * v, 0));
  const normR = Math.sqrt(rv.reduce((s, v) => s + v * v, 0));

  return dot / (normC * normR); // cosine similarity
}
```

## 4. Logo Perceptual Hash Check (Avatar Upload Hook)

```typescript
// src/crisis-logo-check.ts
// Uses Workers AI image classification as a proxy for logo similarity
export async function checkAvatarForCrisisLogo(
  imageBuffer: ArrayBuffer,
  env: Env
): Promise<{ suspicious: boolean; serviceId: string | null }> {
  // Classify image for known crisis branding keywords
  const result = await env.AI.run(
    "@cf/microsoft/resnet-50",
    { image: [...new Uint8Array(imageBuffer)] }
  );

  // Heuristic: crisis org logos often classify as "label," "text," "signage"
  // Full phash comparison would require a custom model or R2 stored references
  const topLabels = result.slice(0, 3).map((r: { label: string }) =>
    r.label.toLowerCase()
  );

  // Check against stored phash in D1 via separate phash computation
  // (placeholder — production uses a Workers phash binding or R2 reference image)
  const suspicious = topLabels.some((l) =>
    ["hotline", "lifeline", "crisis", "988"].some((k) => l.includes(k))
  );

  return { suspicious, serviceId: suspicious ? "manual-review" : null };
}
```

## 5. Composite Gating & Enforcement

```typescript
// src/crisis-gate.ts
import { checkHandleForCrisisImpersonation } from "./crisis-handle-check";
import { scoreBioSimilarity } from "./crisis-bio-check";
import { checkAvatarForCrisisLogo } from "./crisis-logo-check";

export async function evaluateNewAccount(
  accountId: string,
  handle: string,
  bio: string,
  avatarBuffer: ArrayBuffer | null,
  env: Env,
  ctx: ExecutionContext
): Promise<"allow" | "hold_for_review" | "reject"> {
  const handleCheck = await checkHandleForCrisisImpersonation(handle, env);

  let score = 0;
  const signals: Record<string, unknown> = {};

  if (handleCheck.match) {
    score += 0.5;
    signals.handle = { serviceId: handleCheck.serviceId, distance: handleCheck.distance };

    if (bio.length > 10 && handleCheck.serviceId) {
      const bioSim = await scoreBioSimilarity(bio, handleCheck.serviceId, env);
      score += bioSim * 0.35;
      signals.bioSimilarity = bioSim;
    }
  }

  if (avatarBuffer) {
    const logoCheck = await checkAvatarForCrisisLogo(avatarBuffer, env);
    if (logoCheck.suspicious) {
      score += 0.25;
      signals.logoSuspicious = true;
    }
  }

  if (score >= 0.75) {
    ctx.waitUntil(
      env.DB.prepare(
        `INSERT INTO crisis_impersonation_reports
         (report_id, account_id, service_id, score, signals, detected_at)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
        .bind(
          crypto.randomUUID(),
          accountId,
          signals.handle?.serviceId ?? "unknown",
          score,
          JSON.stringify(signals),
          Date.now()
        )
        .run()
    );
    return score >= 0.9 ? "reject" : "hold_for_review";
  }

  return "allow";
}
```

## 6. Evidence Snapshot to R2 (Law Enforcement Escalation)

```typescript
// src/crisis-evidence.ts
export async function snapshotForEscalation(
  reportId: string,
  accountData: object,
  env: Env
): Promise<string> {
  const key = `crisis-impersonation/${reportId}.json`;
  await env.EVIDENCE_BUCKET.put(key, JSON.stringify({
    capturedAt: new Date().toISOString(),
    reportId,
    accountData,
  }), {
    httpMetadata: { contentType: "application/json" },
    customMetadata: { legalHold: "true", retentionDays: "730" },
  });
  return key;
}
```

## Anti-patterns

- Relying on exact handle match only — impersonators use look-alike characters (e.g., "988Iifeline" with lowercase L).
- Applying bio similarity without a handle match first — unrelated accounts may legitimately mention crisis resources.
- Storing avatar hash in KV only — phash data must survive KV eviction; store in D1 with R2 backup.
- Restricting the registry to English-language services — platforms with international users must include Samaritans (UK), Telefonseelsorge (DE), SOS Amitié (FR), etc.

## Gotchas

- Workers have a 128 MB memory limit; loading full avatar buffers for logo comparison counts toward this — stream large images via R2 multipart rather than buffering in-flight.
- Edit distance of 2 can over-fire on very short handles (< 5 chars); add a length-relative threshold (distance / handle length < 0.33).
- Crisis registries change phone numbers and handles; schedule a weekly ingestion job (Cron Trigger) to pull from SAMHSA and equivalent APIs.
- `hold_for_review` accounts must not be able to send DMs during review; ensure the enforcement action sets `can_dm = false` in the accounts table.

## Verification

```bash
# Confirm registry loaded
wrangler d1 execute example project-prod --command \
  "SELECT canonical_name, country_code FROM crisis_services ORDER BY country_code"

# Simulate impersonation attempt in staging
curl -X POST https://staging.example.com/api/accounts \
  -d '{"handle":"988lifellne","bio":"Call us anytime — 988 Suicide Lifeline"}'
# Expect HTTP 403 or 202 (hold_for_review)

# Check recent impersonation reports
wrangler d1 execute example project-prod --command \
  "SELECT account_id, service_id, score, action FROM crisis_impersonation_reports \
   ORDER BY detected_at DESC LIMIT 20"
```

## Related

- `anonymous-user-impersonation-detection-workers.md`
- `brand-impersonation-detection-takedown.md`
- `crisis-intervention-detection-workers-ai.md`
- `self-harm-content-detection-workers-ai.md`
- `legal-hold-evidence-preservation-d1-r2.md`

## Sources

- SAMHSA 988 Lifeline (samhsa.gov/find-help/988-suicide-crisis-lifeline)
- FTC — Impersonation Rule (ftc.gov/legal-library/browse/rules/impersonation-rule)
- EU DSA Art. 26 — Systemic Risk Assessment requirements
- Cloudflare Workers AI — image classification models (developers.cloudflare.com/workers-ai/models/)
