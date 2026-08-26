# Predatory Pricing & Dark Pattern Detection — Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

example project allows third-party creators to sell digital goods (sticker packs, premium posts,
community badges) through its platform. Some creators use manipulative pricing tactics —
artificial scarcity countdowns, drip-releasing identical content under new SKUs, anchoring
with inflated "original" prices, or hidden mandatory tip fields. These dark patterns harm
users, expose example project to DSA / consumer protection liability, and erode platform trust. This
article covers how to detect them automatically using Workers AI and structured listing
analysis, before they go live.

---

## Context

Dark patterns in digital goods listings share detectable linguistic and structural features:
- **False urgency** — "Only 2 left!", countdown timers disconnected from actual stock.
- **Price anchoring** — displaying a struck-through "was $49.99" that was never a real price.
- **Hidden fees** — listing price excludes mandatory add-ons revealed only at checkout.
- **Confirmshaming** — opt-out text phrased as self-degrading ("No thanks, I prefer being
  poor").
- **Content reskins** — same asset uploaded multiple times with trivially different metadata
  to manufacture artificial scarcity across SKUs.

Workers AI handles text classification (linguistic patterns) and image embeddings (reskin
detection). D1 stores the listing metadata and audit trail.

---

## Schema

```sql
CREATE TABLE listings (
  id              TEXT PRIMARY KEY,
  creator_id      TEXT NOT NULL,
  title           TEXT NOT NULL,
  description     TEXT,
  price_cents     INTEGER NOT NULL,
  anchor_price    INTEGER,          -- displayed "was" price (nullable)
  stock_count     TEXT,             -- "3 left" string or NULL
  created_at      INTEGER NOT NULL,
  reviewed        INTEGER DEFAULT 0,
  dark_pattern    INTEGER DEFAULT 0,
  dp_flags        TEXT              -- JSON array of detected flags
);

CREATE INDEX idx_listings_creator ON listings (creator_id, created_at);
CREATE INDEX idx_listings_dp      ON listings (dark_pattern, reviewed);
```

---

## 1. Linguistic Dark Pattern Classification

Use Workers AI zero-shot classification to detect manipulative framing in listing text.

```typescript
const DARK_PATTERN_LABELS = [
  "false_urgency",
  "price_anchoring",
  "confirmsham",
  "neutral",
] as const;

type DPLabel = (typeof DARK_PATTERN_LABELS)[number];

interface DPClassification {
  label: DPLabel;
  score: number;
}

async function classifyListingText(
  ai: Ai,
  title: string,
  description: string
): Promise<DPClassification[]> {
  const combined = `${title}. ${description ?? ""}`.slice(0, 1000);
  const result = await ai.run("@cf/facebook/bart-large-mnli", {
    text: combined,
    candidate_labels: [...DARK_PATTERN_LABELS],
  });

  return result.labels.map((label: string, i: number) => ({
    label: label as DPLabel,
    score: result.scores[i] as number,
  }));
}
```

---

## 2. Anchor Price Validity Check

An anchor price is suspicious if it has never been the actual listed price within the last
90 days, or if it exceeds the current price by more than 10x.

```typescript
async function validateAnchorPrice(
  db: D1Database,
  creatorId: string,
  currentPrice: number,
  anchorPrice: number | null
): Promise<{ suspicious: boolean; reason?: string }> {
  if (anchorPrice === null) return { suspicious: false };

  if (anchorPrice > currentPrice * 10) {
    return { suspicious: true, reason: "anchor_exceeds_10x_current" };
  }

  // Check price history (requires a price_history table to be populated on each update)
  const row = await db
    .prepare(
      `SELECT 1 FROM price_history
       WHERE creator_id = ? AND price_cents = ? AND recorded_at > ?
       LIMIT 1`
    )
    .bind(creatorId, anchorPrice, Date.now() - 90 * 86_400_000)
    .first();

  if (!row) {
    return { suspicious: true, reason: "anchor_price_never_listed" };
  }

  return { suspicious: false };
}
```

---

## 3. False Scarcity Detection

Parse stock count strings and correlate against actual inventory records.

```typescript
const SCARCITY_PATTERNS = [
  /only\s+\d+\s+left/i,
  /\d+\s+remaining/i,
  /limited\s+stock/i,
  /selling\s+fast/i,
  /almost\s+gone/i,
];

function containsScarcityClaim(text: string): boolean {
  return SCARCITY_PATTERNS.some((re) => re.test(text));
}

async function validateScarcityClaim(
  db: D1Database,
  listingId: string,
  claimedStock: string | null
): Promise<{ suspicious: boolean; reason?: string }> {
  if (!claimedStock) return { suspicious: false };
  if (!containsScarcityClaim(claimedStock)) return { suspicious: false };

  // Check actual digital goods stock — digital goods never run out; claim is inherently false
  const { results } = await db
    .prepare(`SELECT good_type FROM listings WHERE id = ?`)
    .bind(listingId)
    .all<{ good_type: string }>();

  const goodType = results[0]?.good_type;
  if (goodType === "digital") {
    return { suspicious: true, reason: "scarcity_claim_on_unlimited_digital_good" };
  }

  return { suspicious: false };
}
```

---

## 4. Content Reskin Detection via Image Embeddings

Detect creators uploading near-identical assets under different SKUs.

```typescript
async function detectReskin(
  ai: Ai,
  db: D1Database,
  creatorId: string,
  newImageBase64: string
): Promise<{ isDuplicate: boolean; matchedListingId?: string }> {
  const response = await ai.run("@cf/baai/bge-base-en-v1.5", {
    text: [`image:${newImageBase64.slice(0, 512)}`], // use image caption or hash as proxy
  });
  const newVec: number[] = response.data[0];

  // Fetch stored embeddings for this creator's recent listings
  const { results } = await db
    .prepare(
      `SELECT id, image_embedding FROM listings
       WHERE creator_id = ? AND image_embedding IS NOT NULL
         AND created_at > ? LIMIT 100`
    )
    .bind(creatorId, Date.now() - 90 * 86_400_000)
    .all<{ id: string; image_embedding: string }>();

  for (const row of results) {
    const existingVec: number[] = JSON.parse(row.image_embedding);
    const sim = cosineSimilarity(newVec, existingVec);
    if (sim > 0.97) {
      return { isDuplicate: true, matchedListingId: row.id };
    }
  }

  return { isDuplicate: false };
}

function cosineSimilarity(a: number[], b: number[]): number {
  const dot = a.reduce((s, v, i) => s + v * b[i], 0);
  const norm = (v: number[]) => Math.sqrt(v.reduce((s, x) => s + x * x, 0));
  return dot / (norm(a) * norm(b));
}
```

---

## 5. Composite Review Gate

Run all checks before a listing goes live and flag or block accordingly.

```typescript
async function reviewListing(
  db: D1Database,
  ai: Ai,
  listing: {
    id: string;
    creatorId: string;
    title: string;
    description: string;
    priceCents: number;
    anchorPrice: number | null;
    stockCount: string | null;
    imageBase64?: string;
  }
): Promise<void> {
  const flags: string[] = [];

  // 1. Text classification
  const textResults = await classifyListingText(ai, listing.title, listing.description);
  const topResult = textResults[0];
  if (topResult.label !== "neutral" && topResult.score > 0.65) {
    flags.push(`linguistic:${topResult.label}:${topResult.score.toFixed(2)}`);
  }

  // 2. Anchor price
  const anchorCheck = await validateAnchorPrice(db, listing.creatorId, listing.priceCents, listing.anchorPrice);
  if (anchorCheck.suspicious) flags.push(`anchor:${anchorCheck.reason}`);

  // 3. Scarcity
  const scarcityCheck = await validateScarcityClaim(db, listing.id, listing.stockCount);
  if (scarcityCheck.suspicious) flags.push(`scarcity:${scarcityCheck.reason}`);

  // 4. Reskin
  if (listing.imageBase64) {
    const reskinCheck = await detectReskin(ai, db, listing.creatorId, listing.imageBase64);
    if (reskinCheck.isDuplicate) flags.push(`reskin:matched:${reskinCheck.matchedListingId}`);
  }

  const isDarkPattern = flags.length > 0;
  await db
    .prepare(
      `UPDATE listings SET reviewed = 1, dark_pattern = ?, dp_flags = ? WHERE id = ?`
    )
    .bind(isDarkPattern ? 1 : 0, JSON.stringify(flags), listing.id)
    .run();
}
```

---

## Anti-patterns

- **Blocking listings with a single low-confidence AI flag** — require either multiple flags
  or a single flag above 0.80 confidence before hard-blocking; route lower confidence
  findings to human review.
- **Only checking at listing creation** — creators update listings to introduce dark patterns
  post-approval; re-run the gate on every significant update.
- **Treating all countdown timers as fraudulent** — a 48-hour flash-sale with a real end
  date is legitimate; only flag countdowns that reset or are detached from actual stock.
- **Storing image base64 in D1** — store in R2, keep only the embedding vector in D1.

---

## Gotchas

- `@cf/facebook/bart-large-mnli` is English-optimised. For multilingual listings, prepend
  a language detection step and route non-English content to `@cf/meta/m2m100-1.2b` for
  translation first.
- The reskin similarity threshold of 0.97 catches near-pixel-identical uploads; lower to 0.93
  to catch colour-shifted or slightly cropped duplicates, but expect more false positives.
- `price_history` must be populated by a separate trigger on each listing update — it does
  not exist in D1 automatically.
- Consumer protection agencies (FTC, CMA, EU DG JUST) treat dark-pattern detection logs as
  evidence of platform awareness; ensure the `dp_flags` audit trail is legally sound and
  retained per your data-retention policy.

---

## Verification

```bash
# Create a listing with obvious false urgency
curl -X POST https://example project.example.com/api/listings \
  -H "Content-Type: application/json" \
  -d '{"title":"Only 1 left - exclusive sticker pack!","price":99,"anchorPrice":999}'

# Check review outcome
wrangler d1 execute example project_DB --command \
  "SELECT id, dark_pattern, dp_flags FROM listings ORDER BY created_at DESC LIMIT 1"
```

Expected: `dark_pattern = 1`, `dp_flags` contains `linguistic:false_urgency` and
`anchor:anchor_price_never_listed`.

---

## Related

- `dark-patterns-deceptive-design-regulation.md`
- `financial-fraud-detection-digital-goods.md`
- `platform-abuse-rate-velocity-d1-workers.md`
- `content-farm-spam-network-detection-d1.md`

---

## Sources

- EU DSA Article 25 — prohibition of dark patterns
- FTC "Bringing Dark Patterns to Light" (2022)
- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- example project creator marketplace policy v2.3
