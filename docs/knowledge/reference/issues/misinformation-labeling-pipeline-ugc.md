# Misinformation Labeling Pipeline for UGC

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A platform hosting user-generated articles, social posts, or community discussions observes viral spread of health misinformation ("drinking bleach cures COVID"), election integrity claims ("polls close at 7pm everywhere in the US"), and financial fraud narratives ("this coin is guaranteed 10x by the SEC"). Moderation relies on reactive user reports, which arrive too late — the content has already been seen by tens of thousands of users before a human reviewer acts.

Secondary complaint: labels applied by automated systems generate more than 25 % false positives on satire and opinion pieces, eroding creator trust. The platform needs a pipeline that (a) surfaces content for review faster than human report queues can, (b) applies contextual informational labels without removing content prematurely, and (c) maintains an auditable decision trail that can demonstrate good-faith compliance to regulators.

## Context

Misinformation is regulated differently from illegal content: it typically does not trigger mandatory removal obligations (unlike CSAM or terrorist content), but DSA Article 34 requires Very Large Online Platforms (VLOPs) with 45 M+ EU users to assess and mitigate systemic risks including "the spreading of disinformation." Mitigation measures must be proportionate — labeling and reduced amplification before outright removal.

The pipeline distinguishes three classes:
- **Health/safety misinformation** — WHO-classified medical myths, vaccine disinformation (highest urgency, potential for physical harm).
- **Civic/electoral misinformation** — voting procedure errors, candidate fabrications (seasonal surge around elections).
- **Financial misinformation** — pump-and-dump language, false SEC/regulatory claims (overlap with financial fraud detection).

Tooling: Cloudflare Workers AI (text classification), D1 (content and label log), KV (claim signature cache for deduplication), Queues (async human review dispatch), and an external fact-check database API (ClaimReview schema, IFCN-certified fact-checkers).

## Automated Claim Extraction and Classification

On content publication or edit, a Worker extracts claim candidates and scores them for misinformation risk using Workers AI.

```typescript
// workers/misinformation-classifier.ts
export interface ContentSubmission {
  contentId: string;
  authorId: string;
  text: string;
  contentType: "article" | "comment" | "post";
  publishedAt: number;
}

export interface ClaimClassification {
  contentId: string;
  claimSignature: string;     // SHA-256 of normalized claim text (for deduplication)
  category: "health" | "civic" | "financial" | "other" | "none";
  confidence: number;         // 0–1
  suggestedLabel: string | null;
  action: "no_action" | "apply_label" | "queue_human_review" | "reduce_amplification";
  modelVersion: string;
}

export async function classifyContent(
  submission: ContentSubmission,
  env: Env
): Promise<ClaimClassification> {
  // 1. Classify misinformation category
  const classifyResponse = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content: `You are a content safety classifier. Analyze the following user-generated text and determine:
1. Whether it contains factual claims that could constitute misinformation.
2. The category: health, civic, financial, or none.
3. Confidence score from 0.0 to 1.0.
Respond in JSON: {"category":"health|civic|financial|other|none","confidence":0.0,"contains_claim":true|false}
Be conservative — return "none" for clear satire, clearly labelled opinion, and content with no factual claims.`,
      },
      { role: "user", content: submission.text.slice(0, 2000) }, // truncate to 2k chars
    ],
  }) as { response: string };

  let classification: { category: ClaimClassification["category"]; confidence: number; contains_claim: boolean };
  try {
    classification = JSON.parse(classifyResponse.response);
  } catch {
    classification = { category: "none", confidence: 0, contains_claim: false };
  }

  if (!classification.contains_claim || classification.confidence < 0.6) {
    return {
      contentId: submission.contentId,
      claimSignature: "",
      category: "none",
      confidence: classification.confidence,
      suggestedLabel: null,
      action: "no_action",
      modelVersion: "llama-3.1-8b",
    };
  }

  // 2. Generate claim signature for deduplication
  const normalized = submission.text.toLowerCase().replace(/\s+/g, " ").trim();
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(normalized));
  const sig = Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");

  // 3. Check claim signature cache — avoid re-classifying the same claim
  const cachedDecision = await env.KV.get(`claim:${sig.slice(0, 32)}`, "json") as
    | Pick<ClaimClassification, "action" | "suggestedLabel">
    | null;
  if (cachedDecision) {
    return {
      contentId: submission.contentId,
      claimSignature: sig,
      category: classification.category,
      confidence: classification.confidence,
      suggestedLabel: cachedDecision.suggestedLabel,
      action: cachedDecision.action,
      modelVersion: "llama-3.1-8b (cached)",
    };
  }

  // 4. Determine action and label based on confidence and category
  let action: ClaimClassification["action"] = "no_action";
  let suggestedLabel: string | null = null;

  if (classification.confidence >= 0.85) {
    if (classification.category === "health") {
      action = "apply_label";
      suggestedLabel = "This post may contain health information that conflicts with guidance from public health authorities.";
    } else if (classification.category === "civic") {
      action = "apply_label";
      suggestedLabel = "This post contains claims about elections or voting. Verify information with official sources.";
    } else if (classification.category === "financial") {
      action = "queue_human_review";
      suggestedLabel = null; // Human decides label text for financial claims
    }
  } else if (classification.confidence >= 0.70) {
    action = "queue_human_review";
  }

  // Cache decision for 7 days to avoid re-classifying identical claims
  await env.KV.put(
    `claim:${sig.slice(0, 32)}`,
    JSON.stringify({ action, suggestedLabel }),
    { expirationTtl: 7 * 24 * 3600 }
  );

  const result: ClaimClassification = {
    contentId: submission.contentId,
    claimSignature: sig,
    category: classification.category,
    confidence: classification.confidence,
    suggestedLabel,
    action,
    modelVersion: "llama-3.1-8b",
  };

  // Log to D1
  await env.DB.prepare(
    `INSERT INTO misinfo_classifications
       (content_id, author_id, claim_signature, category, confidence, suggested_label, action, model_version, ts)
     VALUES (?,?,?,?,?,?,?,?,?)`
  ).bind(
    submission.contentId, submission.authorId, sig.slice(0, 32),
    result.category, result.confidence, result.suggestedLabel,
    result.action, result.modelVersion, Date.now()
  ).run();

  return result;
}
```

## External Fact-Check API Integration

Cross-reference against a ClaimReview database (e.g., Google Fact Check API, Duke Reporters' Lab) before applying a label, to anchor the label to a third-party source.

```typescript
// workers/fact-check-lookup.ts
export interface FactCheckResult {
  found: boolean;
  reviewUrl?: string;
  verdict?: "false" | "mostly_false" | "misleading" | "unproven" | "true";
  factChecker?: string;   // IFCN-certified publisher name
  reviewedAt?: string;
}

export async function lookupClaimReview(
  claimText: string,
  env: Env
): Promise<FactCheckResult> {
  // Google Fact Check Tools API — free, 1000 req/day quota
  const query = encodeURIComponent(claimText.slice(0, 200));
  const url = `https://factchecktools.googleapis.com/v1alpha1/claims:search?query=${query}&key=<redacted-secret>&languageCode=en`;

  let response: Response;
  try {
    response = await fetch(url, { headers: { "Accept": "application/json" } });
  } catch {
    return { found: false };
  }

  if (!response.ok) return { found: false };
  const data = await response.json<{ claims?: Array<{
    claimReview: Array<{
      url: string;
      textualRating: string;
      publisher: { name: string };
      reviewDate: string;
    }>;
  }> }>();

  const claim = data.claims?.[0];
  const review = claim?.claimReview?.[0];
  if (!review) return { found: false };

  // Map textual rating to structured verdict
  const rating = review.textualRating.toLowerCase();
  let verdict: FactCheckResult["verdict"] = "unproven";
  if (rating.includes("false") || rating.includes("incorrect")) verdict = "false";
  else if (rating.includes("mostly false") || rating.includes("mostly incorrect")) verdict = "mostly_false";
  else if (rating.includes("misleading")) verdict = "misleading";
  else if (rating.includes("true")) verdict = "true";

  return {
    found: true,
    reviewUrl: review.url,
    verdict,
    factChecker: review.publisher.name,
    reviewedAt: review.reviewDate,
  };
}
```

## Label Application and Amplification Reduction

Apply labels without removing content. Reduce algorithmic amplification for content with confirmed misinformation labels.

```typescript
// workers/label-applicator.ts
import type { ClaimClassification } from "./misinformation-classifier";
import type { FactCheckResult } from "./fact-check-lookup";

export async function applyMisinformationLabel(
  classification: ClaimClassification,
  factCheck: FactCheckResult,
  env: Env
): Promise<void> {
  if (classification.action === "no_action") return;
  if (classification.action === "queue_human_review") {
    await env.REVIEW_QUEUE.send({
      type: "misinfo_human_review",
      contentId: classification.contentId,
      category: classification.category,
      confidence: classification.confidence,
      claimSignature: classification.claimSignature,
      factCheck,
    });
    return;
  }

  // Construct label with optional fact-check citation
  let labelText = classification.suggestedLabel ?? "This post contains claims that may need verification.";
  let labelSource: string | null = null;
  let labelSourceUrl: string | null = null;

  if (factCheck.found && factCheck.verdict !== "true") {
    labelText = `Fact-checked by ${factCheck.factChecker}: rated "${factCheck.verdict}".`;
    labelSource = factCheck.factChecker ?? null;
    labelSourceUrl = factCheck.reviewUrl ?? null;
  }

  // Insert label record
  await env.DB.prepare(
    `INSERT INTO content_labels
       (content_id, label_type, label_text, label_source, label_source_url,
        auto_applied, applied_at, reviewed_by)
     VALUES (?,?,?,?,?,1,?,NULL)`
  ).bind(
    classification.contentId, "misinformation",
    labelText, labelSource, labelSourceUrl, Date.now()
  ).run();

  // Reduce algorithmic amplification score for feed ranking
  await env.DB.prepare(
    "UPDATE content SET amplification_score = amplification_score * 0.2 WHERE id = ?"
  ).bind(classification.contentId).run();

  // KV flag for CDN edge — edge Workers can check this to inject label banner
  await env.KV.put(
    `content_label:${classification.contentId}`,
    JSON.stringify({ labelText, labelSource, labelSourceUrl, appliedAt: Date.now() }),
    { expirationTtl: 30 * 24 * 3600 }
  );
}

// Edge Worker: inject label banner into content responses
export async function injectLabelBannerIfFlagged(
  contentId: string,
  htmlResponse: string,
  env: Env
): Promise<string> {
  const label = await env.KV.get(`content_label:${contentId}`, "json") as
    | { labelText: string; labelSourceUrl?: string }
    | null;
  if (!label) return htmlResponse;

  const banner = `<div role="note" aria-label="Content label" class="misinfo-label-banner">
    <svg aria-hidden="true" width="16" height="16"><!-- info icon --></svg>
    <span>${escapeHtml(label.labelText)}</span>
    ${label.labelSourceUrl
      ? `<a  target="_blank" rel="noopener">Learn more</a>`
      : ""}
  </div>`;

  return htmlResponse.replace("<article", `${banner}<article`);
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
```

## Human Review Queue Processing

High-stakes decisions (civic/electoral misinformation, financial claims, borderline confidence) require a human reviewer before a label is applied.

```typescript
// workers/misinfo-review-queue-consumer.ts
export interface MisinfoReviewJob {
  type: "misinfo_human_review";
  contentId: string;
  category: string;
  confidence: number;
  claimSignature: string;
  factCheck: { found: boolean; verdict?: string; reviewUrl?: string; factChecker?: string };
}

export async function processMisinfoReviewJob(
  job: MisinfoReviewJob,
  env: Env
): Promise<void> {
  // Insert into reviewer dashboard queue with priority
  const priority = job.category === "civic" || job.confidence > 0.9 ? "high" : "normal";

  await env.DB.prepare(
    `INSERT INTO review_queue
       (content_id, queue_type, priority, metadata, status, queued_at)
     VALUES (?,?,?,?,?,?)`
  ).bind(
    job.contentId, "misinfo", priority,
    JSON.stringify({
      category: job.category,
      confidence: job.confidence,
      factCheck: job.factCheck,
    }),
    "pending", Date.now()
  ).run();

  // Slack alert for high-priority items
  if (priority === "high") {
    await fetch(env.SLACK_WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `:warning: *High-priority misinfo review needed*\nContent: ${job.contentId}\nCategory: ${job.category}\nConfidence: ${(job.confidence * 100).toFixed(0)}%\nFact-check: ${job.factCheck.found ? job.factCheck.verdict : "not found"}\nDashboard: https://admin.example.com/review/${job.contentId}`,
      }),
    });
  }
}
```

## Anti-patterns

- **Applying misinformation labels to clearly labeled satire** — satire and parody are protected speech; the classifier should be tuned to reduce false-positive rates on content with explicit satire disclaimers. Evaluate precision on satire corpus before deploying.
- **Removing content before a human reviews it based solely on model output** — an LLM-only pipeline removing content is legally precarious; the DSA requires proportionate measures. Label first, remove only after escalated human review or clear policy violation.
- **Surfacing the label decision to users in a way that reveals model internals** — label text should reference the policy or the third-party fact-check, not expose confidence scores or model names; scores are gameable once public.
- **Not expiring KV claim-signature caches** — a claim that was falsely classified as misinfo will be permanently cached; use TTL-bounded caches and re-evaluate after significant model updates.
- **Conflating opinion with misinformation** — "I believe the vaccine rollout was poorly managed" is an opinion; "vaccines cause autism, proven by Harvard" is a false factual claim. The classifier system prompt must enforce this distinction rigorously.
- **Processing at publication time synchronously** — the classifier adds latency (300–800 ms for LLM inference). Fire classification asynchronously via Queues and apply labels post-publish; never block content creation on classifier response.

## Gotchas

- Workers AI `@cf/meta/llama-3.1-8b-instruct` has a context window of ~8k tokens; truncating at 2000 characters (above) is conservative and avoids context overflow but may miss relevant claim context in long articles. Consider extracting claim sentences with a lighter heuristic (sentences ending with a verifiable assertion) before sending to the LLM.
- The Google Fact Check Tools API has a 1,000 request/day free quota. For production volumes, cache results by claim signature in KV (TTL 30 days) and fall back to `{ found: false }` gracefully when quota is exceeded — do not throw.
- `JSON.parse` on LLM output will throw if the model wraps the JSON in markdown code fences (```json ... ```). Strip code fences before parsing: `response.replace(/^```json\s*/m, "").replace(/\s*```$/m, "")`.
- KV label flags at the CDN edge are eventually consistent — a label may be visible at some edge nodes seconds before others. If label visibility must be immediate (e.g., breaking election misinformation), bypass the KV cache and serve labels from a D1 read per request.
- The amplification-score multiplier (`* 0.2`) is irreversible if applied directly in SQL; store the original score separately or track the modifier as a column so it can be reversed if a label is appealed and overturned.
- DSA VLOP obligations apply only to platforms with 45 million or more average monthly EU users. Smaller platforms face lighter obligations but may voluntarily adopt this pipeline to prepare for growth.

## Verification

```bash
# 1. Submit known health misinfo claim and confirm it is classified and labeled
curl -X POST https://api.example.com/content \
  -H "Authorization: Bearer <author_token>" \
  -d '{"text":"Drinking bleach cures respiratory infections, confirmed by the CDC."}'
# After async classification (check in ~5s):
wrangler kv key get --binding=KV "content_label:<contentId>"
# Expect: JSON with labelText present

# 2. Submit clear satire and confirm no label applied
curl -X POST https://api.example.com/content \
  -d '{"text":"[SATIRE] Local man cures cold by staring directly at sun for 3 hours"}'
wrangler kv key get --binding=KV "content_label:<contentId>"
# Expect: null (no label)

# 3. Query D1 for classification accuracy in last 24h
wrangler d1 execute DB --command \
  "SELECT category, action, COUNT(*) as n, AVG(confidence) as avg_conf \
   FROM misinfo_classifications WHERE ts > (strftime('%s','now')-86400)*1000 \
   GROUP BY category, action"

# 4. Check review queue depth (should not accumulate unboundedly)
wrangler d1 execute DB --command \
  "SELECT priority, COUNT(*) as pending FROM review_queue \
   WHERE status='pending' AND queue_type='misinfo' GROUP BY priority"

# 5. Verify amplification score reduced on labeled content
wrangler d1 execute DB --command \
  "SELECT id, amplification_score FROM content WHERE id='<contentId>'"
```

## Related

- `spam-post-detection-cloudflare-workers-ai.md` — Workers AI classification patterns
- `deepfake-detection-policy-2026.md` — synthetic media is a vector for misinfo
- `content-moderation-appeals-workflow.md` — appeals for labeled content
- `ai-watermarking-provenance-c2pa-2026.md` — C2PA provenance helps identify AI-generated misinfo
- `dsa-risk-assessment.md` — DSA systemic risk assessments mandate misinfo mitigation
- `eu-dsa-recommender-2026.md` — reduced amplification as a proportionate measure

## Sources

- EU Digital Services Act (DSA) — Articles 14, 16, 22, 34 (VLOP systemic risk obligations)
- EU Code of Practice on Disinformation 2022 (voluntary commitment framework)
- ClaimReview schema — `schema.org/ClaimReview`
- Google Fact Check Tools API — `developers.google.com/fact-check/tools/api`
- International Fact-Checking Network (IFCN) principles — `ifcncodeofprinciples.poynter.org`
- Cloudflare Workers AI — `developers.cloudflare.com/workers-ai`
- First Draft News — Misinformation detection guidelines (2024)
