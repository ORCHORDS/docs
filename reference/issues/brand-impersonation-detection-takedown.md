# Brand Impersonation Detection and Takedown

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A brand's trust-and-safety team receives user reports of fake accounts mimicking their official presence: usernames like `@apple_support_official`, `@paypal_security_team`, or `@nike_official_store` that solicit credentials, payment, or personal information from confused users. Separately, phishing pages hosted on the platform copy the brand's logo, color scheme, and product names to run gift-card or credential-harvesting scams.

A second vector: sellers listing counterfeit physical or digital goods under authentic brand names ("Original Nike Air Max — factory direct") when they have no legitimate relationship with the brand.

The platform faces liability exposure under DSA Article 22 (trusted flaggers), EU Trademark Regulation 2017/1001, US Lanham Act § 32 (trademark infringement), and UDRP proceedings if the platform passively hosts impersonation at scale.

## Context

Brand impersonation differs from copyright infringement (covered separately in `copyright-dmca-takedown-worker-pipeline.md`): it targets trademark rights and consumer deception rather than creative works. The signal set is broader — username similarity, profile imagery, behavioral signals, and listing text — and the takedown pathway involves both the brand's legal team and the platform's Trust & Safety function.

Detection combines three layers:
1. **Automated heuristics** at account creation and listing publication (fuzzy-match against verified-brand name registry, image hash comparison).
2. **Trusted-flagger escalation** for recognized brand safety teams (DSA Article 22 status grants expedited processing).
3. **Periodic crawls** of live accounts to catch impersonation introduced post-creation (name changes, bio edits, profile photo swaps).

The stack: Cloudflare Workers AI (text classification and image captioning), D1 (brand registry and impersonation log), KV (recent verified hashes), R2 (profile image archive for evidence preservation).

## Brand Registry and Verified Entity System

Brands enroll via a vetting process (trademark registration submission + domain verification). The registry lives in D1 and is preloaded into a KV prefix at Worker startup for sub-millisecond lookup.

```typescript
// workers/brand-registry.ts
export interface BrandEntry {
  brandId: string;
  canonicalName: string;            // "Apple", "PayPal", "Nike"
  aliases: string[];                // ["apple inc", "apple computer"]
  officialUsernames: string[];      // ["@apple", "@applemusic"]
  logoHashes: string[];             // perceptual hash of official logos
  verifiedAccountIds: string[];     // platform account IDs granted verified status
  trustedFlaggers: string[];        // DSA trusted-flagger contact emails
  trademarkJurisdictions: string[]; // ["US", "EU", "UK"]
}

export async function loadBrandRegistry(env: Env): Promise<Map<string, BrandEntry>> {
  // Check KV cache first (TTL 1 hour)
  const cached = await env.KV.get("brand_registry:v1", "json") as BrandEntry[] | null;
  if (cached) {
    return new Map(cached.map((b) => [b.brandId, b]));
  }

  const rows = await env.DB.prepare(
    "SELECT * FROM brand_registry WHERE active = 1"
  ).all<BrandEntry>();

  const registry = new Map(rows.results.map((b) => [b.brandId, b]));
  // Populate aliases index for fast fuzzy lookup
  await env.KV.put(
    "brand_registry:v1",
    JSON.stringify(rows.results),
    { expirationTtl: 3600 }
  );
  return registry;
}

// Levenshtein distance — detect typosquatting
function levenshtein(a: string, b: string): number {
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0))
  );
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1]
        : 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
  return dp[m][n];
}

export function matchesBrand(
  candidate: string,
  registry: Map<string, BrandEntry>
): { brandId: string; matchType: string; distance: number } | null {
  const norm = candidate.toLowerCase().replace(/[^a-z0-9]/g, "");

  for (const [brandId, entry] of registry) {
    // Exact match on official usernames
    if (entry.officialUsernames.some((u) => u.toLowerCase().replace(/^@/, "") === norm)) {
      return null; // Legitimate account — skip
    }

    // Check canonical name and aliases for impersonation
    const targets = [entry.canonicalName, ...entry.aliases].map((s) =>
      s.toLowerCase().replace(/[^a-z0-9]/g, "")
    );

    for (const target of targets) {
      if (target.length < 4) continue; // Skip short names (too many false positives)
      const dist = levenshtein(norm, target);
      const similarity = 1 - dist / Math.max(norm.length, target.length);

      if (similarity >= 0.85) {
        const matchType = similarity === 1.0 ? "exact" : "fuzzy";
        return { brandId, matchType, distance: dist };
      }

      // Substring containment: "appleofficialsupport" contains "apple"
      if (norm.includes(target) && norm !== target) {
        return { brandId, matchType: "substring", distance: 0 };
      }
    }
  }
  return null;
}
```

## Profile Image Perceptual Hash Comparison

When a new account sets a profile photo, compute a difference-hash (dHash) and compare against known brand logo hashes stored in KV.

```typescript
// workers/image-phash.ts
// dHash: resize to 9x8, diff adjacent pixels, produce 64-bit fingerprint
// Implemented via Workers AI image transformation or a lightweight canvas approach

export async function computeDHash(imageBuffer: ArrayBuffer): Promise<string> {
  // Use Workers AI image-to-text model for feature extraction,
  // or implement dHash via a small Wasm module.
  // For illustration, we call a hypothetical /dHash endpoint on a bound service.
  const response = await fetch("https://image-hash.internal/dhash", {
    method: "POST",
    body: imageBuffer,
    headers: { "Content-Type": "image/jpeg" },
  });
  const { hash } = await response.json<{ hash: string }>();
  return hash;
}

function hammingDistance(a: string, b: string): number {
  // a and b are 16-char hex strings (64-bit hash)
  let dist = 0;
  for (let i = 0; i < a.length; i++) {
    const xor = parseInt(a[i], 16) ^ parseInt(b[i], 16);
    dist += xor.toString(2).split("").filter((c) => c === "1").length;
  }
  return dist;
}

export async function isLogoImpersonation(
  imageBuffer: ArrayBuffer,
  brandId: string,
  env: Env
): Promise<boolean> {
  const candidateHash = await computeDHash(imageBuffer);
  const knownHashesRaw = await env.KV.get(`brand_logo_hashes:${brandId}`, "json") as string[] | null;
  if (!knownHashesRaw) return false;

  // dHash threshold: Hamming distance <= 10 out of 64 bits (~85% similarity)
  return knownHashesRaw.some((known) => hammingDistance(candidateHash, known) <= 10);
}
```

## Automated Detection Workflow at Account and Listing Creation

```typescript
// workers/impersonation-detector.ts
import { loadBrandRegistry, matchesBrand } from "./brand-registry";
import { isLogoImpersonation } from "./image-phash";

export interface ImpersonationCheckResult {
  flagged: boolean;
  brandId?: string;
  matchType?: string;
  signals: string[];
  action: "allow" | "queue_review" | "auto_suspend";
}

export async function checkNewAccount(
  accountId: string,
  username: string,
  displayName: string,
  bio: string,
  profileImageBuffer: ArrayBuffer | null,
  env: Env
): Promise<ImpersonationCheckResult> {
  const registry = await loadBrandRegistry(env);
  const signals: string[] = [];

  // 1. Username fuzzy match
  const usernameMatch = matchesBrand(username, registry);
  if (usernameMatch) {
    signals.push(`username_match:${usernameMatch.matchType}:${usernameMatch.brandId}`);
  }

  // 2. Display name match
  const displayMatch = matchesBrand(displayName, registry);
  if (displayMatch) {
    signals.push(`display_name_match:${displayMatch.matchType}:${displayMatch.brandId}`);
  }

  // 3. Bio mentions official-sounding terms alongside brand name
  const officialKeywords = /\b(official|verified|support|headquarters|corporate|authentic)\b/i;
  if (officialKeywords.test(bio) && (usernameMatch || displayMatch)) {
    signals.push("bio_official_claim");
  }

  // 4. Logo similarity
  const brandId = usernameMatch?.brandId ?? displayMatch?.brandId;
  if (profileImageBuffer && brandId) {
    const logoMatch = await isLogoImpersonation(profileImageBuffer, brandId, env);
    if (logoMatch) signals.push("logo_similarity");
  }

  const signalCount = signals.length;
  let action: ImpersonationCheckResult["action"] = "allow";
  if (signalCount >= 3) action = "auto_suspend";
  else if (signalCount >= 1) action = "queue_review";

  if (signals.length > 0) {
    // Log to D1 and preserve profile image as evidence in R2
    const evidenceKey = `impersonation/${accountId}/${Date.now()}.jpg`;
    if (profileImageBuffer) {
      await env.R2.put(evidenceKey, profileImageBuffer);
    }

    await env.DB.prepare(
      `INSERT INTO impersonation_reports
         (account_id, username, brand_id, signals, action, evidence_key, ts, status)
       VALUES (?,?,?,?,?,?,?,'open')`
    ).bind(
      accountId, username, brandId ?? null,
      JSON.stringify(signals), action, profileImageBuffer ? evidenceKey : null, Date.now()
    ).run();

    // Notify trusted flaggers for affected brand
    if (brandId) {
      env.ctx.waitUntil(notifyTrustedFlaggers(brandId, accountId, signals, registry, env));
    }
  }

  return {
    flagged: signals.length > 0,
    brandId,
    matchType: usernameMatch?.matchType ?? displayMatch?.matchType,
    signals,
    action,
  };
}

async function notifyTrustedFlaggers(
  brandId: string,
  accountId: string,
  signals: string[],
  registry: Map<string, { trustedFlaggers: string[] } & Record<string, unknown>>,
  env: Env
): Promise<void> {
  const brand = registry.get(brandId);
  if (!brand || brand.trustedFlaggers.length === 0) return;

  for (const email of brand.trustedFlaggers) {
    await fetch("https://api.postmarkapp.com/email", {
      method: "POST",
      headers: {
        "X-Postmark-Server-Token": env.POSTMARK_TOKEN,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        From: "trust-safety@example.com",
        To: email,
        Subject: `[Brand Safety] Potential impersonation of ${brandId} — Account ${accountId}`,
        TextBody: `Signals: ${signals.join(", ")}\nReview: https://admin.example.com/impersonation/${accountId}`,
      }),
    });
  }
}
```

## Takedown Decision and Evidence Packaging

When a reviewer confirms impersonation, the system suspends the account, generates an evidence package for legal records, and sends a DSA-compliant notice.

```typescript
// workers/takedown-executor.ts
export async function executeImpersonationTakedown(
  reportId: string,
  reviewerDecision: "confirmed" | "dismissed",
  env: Env
): Promise<void> {
  const report = await env.DB.prepare(
    "SELECT * FROM impersonation_reports WHERE id = ?"
  ).bind(reportId).first<{
    account_id: string; brand_id: string; username: string;
    signals: string; evidence_key: string | null;
  }>();
  if (!report) throw new Error("Report not found");

  const now = Date.now();
  await env.DB.prepare(
    "UPDATE impersonation_reports SET status = ?, resolved_at = ? WHERE id = ?"
  ).bind(reviewerDecision, now, reportId).run();

  if (reviewerDecision === "dismissed") return;

  // Suspend account
  await env.DB.prepare(
    "UPDATE accounts SET status = 'suspended', suspension_reason = 'brand_impersonation', suspended_at = ? WHERE id = ?"
  ).bind(now, report.account_id).run();

  // Generate DSA Article 17 notice — platform must inform the user
  const noticeKey = `takedown-notices/${report.account_id}/${now}.json`;
  const notice = {
    groundsForRemoval: "brand_impersonation",
    legalBasis: "EU DSA Article 3(b) — illegal content; EU Trademark Regulation 2017/1001",
    brandAffected: report.brand_id,
    detectedSignals: JSON.parse(report.signals),
    appealInstructions: "https://example.com/appeals",
    issuedAt: new Date(now).toISOString(),
  };
  await env.R2.put(noticeKey, JSON.stringify(notice, null, 2));

  // Send notice to the user's email on file
  await sendTakedownNotice(report.account_id, notice, env);
}

declare function sendTakedownNotice(
  accountId: string,
  notice: Record<string, unknown>,
  env: Env
): Promise<void>;
```

## Anti-patterns

- **Auto-suspending purely on username similarity without a second signal** — a user named "apple_lover_1992" will get false-positively suspended; require at least two corroborating signals before auto-suspension.
- **Not preserving evidence before suspension** — once an account is suspended, profile images are often purged. Archive to R2 before action, not after.
- **Processing takedown requests on a first-come basis without verifying the reporter** — a competitor can abuse a takedown API to silence rivals; verify reporter identity and brand ownership before actioning any complaint.
- **Sending the same dHash algorithm parameters to external parties in error messages** — attackers who know the perceptual hash parameters can craft adversarial images that defeat the check.
- **Using exact-string matching only** — "PayPa1" (numeral 1 instead of l) defeats exact match but not Levenshtein; always use fuzzy matching.
- **Failing to implement an appeals path** — DSA Article 20 requires platforms to provide an effective internal complaint-handling system; auto-suspensions without appeal violate this.

## Gotchas

- Levenshtein distance is symmetric but the normalization denominator (`max(a.length, b.length)`) is not — a 6-character brand name matched against a 20-character username with 3 edits has a 0.85 similarity score, but most of the candidate username is unrelated to the brand. Add a length-ratio guard: reject matches where `candidateLen > 2 * brandNameLen`.
- Profile images served via CDN may be transcoded to WebP; your dHash implementation must handle WebP as well as JPEG/PNG. Check the `Content-Type` of the image before hashing.
- KV's `json` type parameter in `get()` calls (`env.KV.get(key, "json")`) returns `null` if the key does not exist, but will throw if the stored value is malformed JSON — wrap in try/catch.
- The DSA trusted-flagger scheme (Article 22) requires the platform to "prioritize" notices, not necessarily to act on them. Define SLAs explicitly in your trusted-flagger agreement (e.g., 48-hour initial review for trademark impersonation).
- Trademark rights are jurisdiction-specific. A brand name protected in the US may not be trademarked in Brazil. Store `trademarkJurisdictions` per brand and apply local law when deciding whether to take down content for users outside those jurisdictions.
- Workers AI image-to-text models cannot reliably determine if an image is a logo versus a photograph of a logo on a product — use perceptual hashing for image-level detection, not AI captioning.

## Verification

```bash
# 1. Test username fuzzy match
curl -X POST https://admin.example.com/internal/impersonation/check-username \
  -H "Authorization: Bearer <admin_token>" \
  -d '{"username":"paypa1_security"}'
# Expect: flagged=true, brandId="paypal", matchType="fuzzy"

# 2. Query open impersonation reports
wrangler d1 execute DB --command \
  "SELECT account_id, username, brand_id, signals, action, status FROM impersonation_reports \
   WHERE status='open' ORDER BY ts DESC LIMIT 20"

# 3. Verify evidence archived in R2
wrangler r2 object list impersonation/ --limit 5

# 4. Check suspended account status
wrangler d1 execute DB --command \
  "SELECT id, status, suspension_reason FROM accounts WHERE status='suspended' \
   AND suspension_reason='brand_impersonation' ORDER BY suspended_at DESC LIMIT 10"

# 5. Smoke-test exact-match bypass for legitimate verified account
curl -X POST https://admin.example.com/internal/impersonation/check-username \
  -d '{"username":"apple"}'
# Expect: flagged=false (official username in registry)
```

## Related

- `copyright-dmca-takedown-worker-pipeline.md` — copyright takedown pipeline (distinct from trademark)
- `digital-services-act-platform-compliance.md` — DSA obligations overview
- `platform-liability-section-230-dsa.md` — platform liability framework
- `content-moderation-appeals-workflow.md` — appeals path required by DSA Article 20
- `spam-post-detection-cloudflare-workers-ai.md` — listing-level spam overlaps with counterfeit detection

## Sources

- EU Digital Services Act (DSA) — Regulation (EU) 2022/2065, Articles 17, 20, 22
- EU Trademark Regulation — Regulation (EU) 2017/1001
- US Lanham Act (15 U.S.C. § 1114) — trademark infringement
- UDRP (Uniform Domain-Name Dispute-Resolution Policy) — WIPO
- Cloudflare Workers AI documentation — `developers.cloudflare.com/workers-ai`
- Cloudflare R2 documentation — `developers.cloudflare.com/r2`
- dHash algorithm — Dr. Neal Krawetz, "Kind of Like That" (2013)
