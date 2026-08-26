# Workers AI Classification with Human Feedback Loop via D1

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

You deploy a text classifier on Workers AI and discover that accuracy degrades on your
specific domain. You need a closed feedback loop: surface model predictions to reviewers,
let them correct labels, store corrections in D1, and use the growing correction dataset
to spot systemic errors, export fine-tuning data, or switch prompt strategies — all without
re-deploying the Worker.

---

## Context

This pattern is called **human-in-the-loop active learning** at the edge. The Worker handles
classification and stores every prediction with its confidence. A review endpoint lets humans
submit corrections. A reporting endpoint surfaces disagreement clusters. The system never
auto-retrains but produces export-ready JSONL for offline fine-tuning.

```
User text → classify Worker → D1 (predictions table)
                                    ↓
             Review UI      → corrections Worker → D1 (corrections table)
                                    ↓
             Reporting Worker → disagreement analysis → JSONL export
```

Primary model: `@cf/facebook/bart-large-mnli` (zero-shot classification) or
`@cf/meta/llama-3.1-8b-instruct` with a few-shot prompt.

---

## 1 · D1 Schema

```sql
-- wrangler d1 execute FEEDBACK_DB --file=schema.sql
CREATE TABLE IF NOT EXISTS predictions (
  id            TEXT    PRIMARY KEY,
  input_text    TEXT    NOT NULL,
  predicted_label TEXT  NOT NULL,
  confidence    REAL    NOT NULL,
  labels_tried  TEXT    NOT NULL,  -- JSON array of candidate labels
  model_id      TEXT    NOT NULL,
  created_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS corrections (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  prediction_id   TEXT    NOT NULL REFERENCES predictions(id),
  correct_label   TEXT    NOT NULL,
  reviewer_id     TEXT    NOT NULL,
  note            TEXT,
  created_at      INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_pred_label  ON predictions(predicted_label);
CREATE INDEX IF NOT EXISTS idx_pred_conf   ON predictions(confidence);
CREATE INDEX IF NOT EXISTS idx_corr_pred   ON corrections(prediction_id);
```

---

## 2 · Classification Worker

```typescript
// workers/classify.ts
import { Ai } from "@cloudflare/ai";
import { nanoid } from "nanoid"; // bundled via npm

export interface Env {
  AI: Ai;
  FEEDBACK_DB: D1Database;
  CANDIDATE_LABELS_KV: KVNamespace; // store label sets per domain
}

const DEFAULT_MODEL = "@cf/facebook/bart-large-mnli";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const {
      text,
      domain = "default",
      storeResult = true,
    }: { text: string; domain?: string; storeResult?: boolean } = await request.json();

    if (!text?.trim()) {
      return new Response(JSON.stringify({ error: "text required" }), { status: 400 });
    }

    // Fetch candidate labels for this domain from KV (fallback to generic set)
    const labelsRaw = await env.CANDIDATE_LABELS_KV.get(`labels:${domain}`);
    const candidateLabels: string[] = labelsRaw
      ? JSON.parse(labelsRaw)
      : ["positive", "negative", "neutral"];

    const aiResult = await env.AI.run(DEFAULT_MODEL, {
      text: text.slice(0, 1024),
      candidate_labels: candidateLabels,
    });

    const topLabel = (aiResult as { label: string }).label;
    const scores = (aiResult as { scores: number[] }).scores;
    const topScore = scores[0] ?? 0;

    const predictionId = nanoid();

    if (storeResult) {
      await env.FEEDBACK_DB.prepare(
        `INSERT INTO predictions
           (id, input_text, predicted_label, confidence, labels_tried, model_id)
         VALUES (?, ?, ?, ?, ?, ?)`
      )
        .bind(
          predictionId,
          text.slice(0, 2000), // store truncated for audit
          topLabel,
          topScore,
          JSON.stringify(candidateLabels),
          DEFAULT_MODEL
        )
        .run();
    }

    return new Response(
      JSON.stringify({
        predictionId,
        label: topLabel,
        confidence: topScore,
        allLabels: candidateLabels.map((l, i) => ({ label: l, score: scores[i] ?? 0 })),
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## 3 · Correction Submission Worker

```typescript
// workers/correct.ts
export interface Env {
  FEEDBACK_DB: D1Database;
}

interface CorrectionPayload {
  predictionId: string;
  correctLabel: string;
  reviewerId: string;
  note?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") return new Response("POST only", { status: 405 });

    const payload: CorrectionPayload = await request.json();
    const { predictionId, correctLabel, reviewerId, note } = payload;

    if (!predictionId || !correctLabel || !reviewerId) {
      return new Response(
        JSON.stringify({ error: "predictionId, correctLabel, reviewerId required" }),
        { status: 400 }
      );
    }

    // Verify the prediction exists before inserting a correction
    const pred = await env.FEEDBACK_DB.prepare(
      "SELECT id, predicted_label FROM predictions WHERE id = ?"
    )
      .bind(predictionId)
      .first<{ id: string; predicted_label: string }>();

    if (!pred) {
      return new Response(JSON.stringify({ error: "Prediction not found" }), { status: 404 });
    }

    const isAgreement = pred.predicted_label === correctLabel;

    await env.FEEDBACK_DB.prepare(
      `INSERT INTO corrections (prediction_id, correct_label, reviewer_id, note)
       VALUES (?, ?, ?, ?)`
    )
      .bind(predictionId, correctLabel, reviewerId, note ?? null)
      .run();

    return new Response(
      JSON.stringify({
        ok: true,
        predictionId,
        originalLabel: pred.predicted_label,
        correctLabel,
        isAgreement,
      }),
      { headers: { "Content-Type": "application/json" } }
    );
  },
};
```

---

## 4 · Disagreement Analytics Worker

```typescript
// workers/analytics.ts
export interface Env {
  FEEDBACK_DB: D1Database;
}

interface DisagreementRow {
  predicted_label: string;
  correct_label: string;
  count: number;
  avg_confidence: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const action = url.searchParams.get("action") ?? "summary";

    if (action === "summary") {
      // Confusion-matrix-style disagreement summary
      const { results } = await env.FEEDBACK_DB.prepare(
        `SELECT p.predicted_label,
                c.correct_label,
                COUNT(*)            AS count,
                AVG(p.confidence)   AS avg_confidence
         FROM corrections c
         JOIN predictions p ON c.prediction_id = p.id
         WHERE c.correct_label != p.predicted_label
         GROUP BY p.predicted_label, c.correct_label
         ORDER BY count DESC
         LIMIT 50`
      ).all<DisagreementRow>();

      return new Response(JSON.stringify({ disagreements: results }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    if (action === "export_jsonl") {
      // Export corrected examples as fine-tuning JSONL
      const limit = Math.min(parseInt(url.searchParams.get("limit") ?? "1000", 10), 5000);

      const { results } = await env.FEEDBACK_DB.prepare(
        `SELECT p.input_text, c.correct_label AS label, c.note
         FROM corrections c
         JOIN predictions p ON c.prediction_id = p.id
         ORDER BY c.created_at DESC
         LIMIT ?`
      )
        .bind(limit)
        .all<{ input_text: string; label: string; note: string | null }>();

      const jsonl = results
        .map((r) => JSON.stringify({ text: r.input_text, label: r.label }))
        .join("\n");

      return new Response(jsonl, {
        headers: {
          "Content-Type": "application/x-ndjson",
          "Content-Disposition": "attachment; filename=corrections.jsonl",
        },
      });
    }

    return new Response(JSON.stringify({ error: "Unknown action" }), { status: 400 });
  },
};
```

---

## 5 · Label Management via KV

```typescript
// Seed candidate labels for a domain
// wrangler kv key put --binding=CANDIDATE_LABELS_KV "labels:support" '["billing","technical","complaint","compliment","other"]'

// Runtime label update endpoint
export async function updateLabels(
  env: { CANDIDATE_LABELS_KV: KVNamespace },
  domain: string,
  labels: string[]
): Promise<void> {
  if (labels.length < 2 || labels.length > 20) {
    throw new Error("Must provide 2–20 candidate labels");
  }
  await env.CANDIDATE_LABELS_KV.put(`labels:${domain}`, JSON.stringify(labels));
}
```

---

## 6 · wrangler.toml

```toml
name = "classifier-feedback"
main = "workers/classify.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[d1_databases]]
binding = "FEEDBACK_DB"
database_name = "classifier-feedback"
database_id = "<YOUR_D1_DB_ID>"

[[kv_namespaces]]
binding = "CANDIDATE_LABELS_KV"
id = "<YOUR_KV_NAMESPACE_ID>"
```

---

## Anti-patterns

- **Auto-applying corrections to the running model** — there is no hot-patch path for Workers AI
  models at runtime; corrections feed offline fine-tuning or prompt updates, not live retraining.
- **Storing corrections without linking to the original prediction** — the `prediction_id`
  foreign key is essential; corrections without predictions cannot be used for analysis.
- **Letting any caller submit corrections** — always authenticate `reviewerId`; anonymous
  corrections pollute the dataset and can be used to bias the model.
- **Exporting uncleaned JSONL** — filter out corrections where `note` contains "unsure" or
  where a prediction has conflicting corrections from multiple reviewers before fine-tuning.
- **Ignoring high-confidence disagreements** — sort by `avg_confidence DESC` in the summary;
  a high-confidence wrong prediction indicates a systematic prompt or label definition flaw.

---

## Gotchas

- `@cf/facebook/bart-large-mnli` returns `{ label, labels, scores }` where `label` is the
  top predicted class and `scores` are sorted descending — not aligned with the input
  `candidate_labels` order. Always zip `labels[i]` with `scores[i]`, not `candidate_labels[i]`.
- D1 does not enforce foreign key constraints by default in SQLite; add `PRAGMA foreign_keys=ON`
  or enforce referential integrity in application logic.
- `nanoid` is not available natively in Workers; either bundle it or use `crypto.randomUUID()`
  (available in Workers runtime since 2022).
- D1 `INSERT` returns `{ meta: { last_row_id } }` not the row itself; use the generated `id`
  you bound as input, not the last_row_id, for the prediction record.
- Zero-shot BART-MNLI accuracy drops significantly with more than 10 candidate labels;
  keep label sets focused per domain.

---

## Verification

```bash
# Classify a support ticket
curl -X POST https://classifier-feedback.workers.dev \
  -H "Content-Type: application/json" \
  -d '{"text": "My invoice shows the wrong amount charged", "domain": "support"}'

# Submit a correction
curl -X POST https://classifier-feedback.workers.dev/correct \
  -H "Content-Type: application/json" \
  -d '{"predictionId":"abc123","correctLabel":"billing","reviewerId":"reviewer@example.com"}'

# View disagreement summary
curl "https://classifier-feedback.workers.dev/analytics?action=summary"

# Export fine-tuning JSONL (top 500 corrected examples)
curl "https://classifier-feedback.workers.dev/analytics?action=export_jsonl&limit=500" \
  -o corrections.jsonl
```

---

## Related

- `workers-ai-text-classification-moderation.md`
- `workers-ai-content-safety-classifier-pipeline.md`
- `llm-eval-harness-ci-regression.md`
- `ai-bias-detection.md`
- `fine-tuning-evaluation.md`

---

## Sources

- Workers AI BART-MNLI model: https://developers.cloudflare.com/workers-ai/models/bart-large-mnli/
- D1 Worker API: https://developers.cloudflare.com/d1/worker-api/
- Active learning survey (Settles, 2012): https://burrsettles.com/pub/settles.activelearning.pdf
- Cloudflare KV: https://developers.cloudflare.com/kv/api/
