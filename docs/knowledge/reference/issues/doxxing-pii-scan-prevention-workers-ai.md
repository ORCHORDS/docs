# Doxxing and PII Scan Prevention via Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Users post other people's home addresses, phone numbers, government ID numbers, and employer details to facilitate real-world harassment. Posts containing PII must be detected and withheld before they reach a public feed.

## Context
Doxxing causes direct physical harm and exposes the platform to liability under EU GDPR Article 9 (special category data) and US state privacy statutes. A regex + AI double-pass running inside a Cloudflare Worker intercepts posts at submission time, extracts candidate PII spans, scores intent, and either auto-removes high-confidence violations or queues borderline cases for human review. The approach must avoid false positives on self-disclosure (users sharing their own contact info in profiles).

## Regex Pre-filter for PII Candidates

A lightweight regex pass runs synchronously in the Worker to avoid burning AI inference tokens on posts with no PII signal. Patterns cover phone numbers, email addresses, US SSNs, postal codes paired with street addresses, and government ID formats.

```typescript
// lib/pii-patterns.ts
export const PII_PATTERNS: Record<string, RegExp> = {
  phone: /(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}/g,
  ssn: /\b(?!000|666|9\d{2})\d{3}[- ]\d{2}[- ]\d{4}\b/g,
  email: /[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}/g,
  street_address:
    /\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Ave|Blvd|Rd|Dr|Ln|Way|Ct)\.?\b/g,
  us_zip: /\b\d{5}(?:-\d{4})?\b/g,
};

export function extractPiiCandidates(text: string): string[] {
  const spans: string[] = [];
  for (const [, pattern] of Object.entries(PII_PATTERNS)) {
    const matches = text.matchAll(new RegExp(pattern.source, pattern.flags));
    for (const m of matches) spans.push(m[0]);
  }
  return [...new Set(spans)];
}
```

## Workers AI Intent Classification

When PII candidates are found, the full post body is sent to Workers AI to determine whether the intent is doxxing (exposing someone else's information with harmful framing) versus benign self-disclosure or journalism.

```typescript
// worker: post-submit.ts
export interface Env {
  DB: D1Database;
  REVIEW_QUEUE: Queue;
  AI: Ai;
}

interface PostPayload {
  postId: string;
  authorId: string;
  body: string;
  submittedAt: string;
}

async function classifyDoxxingIntent(
  body: string,
  candidates: string[],
  env: Env
): Promise<{ score: number; reason: string }> {
  const prompt =
    `Post content:\n"""\n${body}\n"""\n\n` +
    `Detected PII spans: ${candidates.join(", ")}\n\n` +
    `Classify whether this post is doxxing another person (sharing their private information ` +
    `without consent to facilitate harassment). Return JSON {score: 0-1, reason: string}. ` +
    `score >= 0.7 = likely doxxing, < 0.3 = likely benign.`;

  const res = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
    messages: [
      {
        role: "system",
        content: "You are a privacy violation classifier for a social platform trust and safety team.",
      },
      { role: "user", content: prompt },
    ],
  }) as { response: string };

  try {
    return JSON.parse(res.response);
  } catch {
    return { score: 0, reason: "parse_error" };
  }
}
```

## Post Submission Gate

The submission worker runs the PII pre-filter and, if candidates are found, calls the classifier. Auto-removes posts above the hard threshold; queues borderline posts; publishes clean posts normally.

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const post = await req.json<PostPayload>();
    const candidates = extractPiiCandidates(post.body);

    if (candidates.length === 0) {
      await publishPost(post, env);
      return new Response(JSON.stringify({ status: "published" }), {
        headers: { "Content-Type": "application/json" },
      });
    }

    const { score, reason } = await classifyDoxxingIntent(
      post.body,
      candidates,
      env
    );

    if (score >= 0.75) {
      // Auto-remove: record removal for transparency report
      await env.DB.prepare(
        `INSERT INTO removed_posts
         (post_id, author_id, reason, pii_score, removed_at)
         VALUES (?, ?, 'doxxing_auto', ?, ?)`
      ).bind(post.postId, post.authorId, score, new Date().toISOString()).run();

      return new Response(
        JSON.stringify({ status: "rejected", reason: "policy_violation" }),
        { status: 422, headers: { "Content-Type": "application/json" } }
      );
    }

    if (score >= 0.4) {
      // Hold for human review — post is not published yet
      await env.DB.prepare(
        `INSERT INTO posts (post_id, author_id, body, submitted_at, status)
         VALUES (?, ?, ?, ?, 'held')`
      ).bind(post.postId, post.authorId, post.body, post.submittedAt).run();

      await env.REVIEW_QUEUE.send({
        postId: post.postId,
        score,
        reason,
        candidates,
        queuedAt: new Date().toISOString(),
      });

      return new Response(
        JSON.stringify({ status: "pending_review" }),
        { headers: { "Content-Type": "application/json" } }
      );
    }

    await publishPost(post, env);
    return new Response(JSON.stringify({ status: "published" }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};

async function publishPost(post: PostPayload, env: Env): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO posts (post_id, author_id, body, submitted_at, status)
     VALUES (?, ?, ?, ?, 'live')`
  ).bind(post.postId, post.authorId, post.body, post.submittedAt).run();
}
```

## Transparency Report Aggregation

Regulators (EU DSA Article 15, DSA Article 24) require periodic transparency reports on removed content. A cron-triggered worker aggregates daily removal counts by category.

```typescript
// worker: transparency-cron.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const today = new Date().toISOString().slice(0, 10);
    const { results } = await env.DB.prepare(
      `SELECT reason, COUNT(*) as count
       FROM removed_posts
       WHERE removed_at >= ? AND removed_at < date(?, '+1 day')
       GROUP BY reason`
    ).bind(today, today).all<{ reason: string; count: number }>();

    await env.DB.prepare(
      `INSERT OR REPLACE INTO transparency_daily (date, data)
       VALUES (?, ?)`
    ).bind(today, JSON.stringify(results)).run();
  },
};
```

## Anti-patterns
- Running AI inference on every post regardless of PII candidates — the regex pre-filter cuts inference costs by ~90% on typical feeds
- Auto-removing posts based solely on regex matches without intent classification — street addresses in restaurant reviews are not doxxing
- Storing unredacted PII spans in the review queue message — store only the `postId` and score; reviewers fetch the full post from D1 via a privileged endpoint
- Applying the same score threshold to verified vs. anonymous accounts — anonymous authors warrant a lower removal threshold

## Gotchas
- `matchAll` requires the `g` flag on the regex; omitting it throws a TypeError in V8
- Workers AI responses occasionally include markdown fences around the JSON — strip ` ```json ` wrappers before `JSON.parse`
- D1 `INSERT OR REPLACE INTO transparency_daily` requires a unique constraint on `date`; create it in your migration
- The 50 ms CPU time limit on bundled Workers can be tight if regex patterns with many alternations run on long posts; keep pattern sets lean

## Verification
1. Submit a post containing a fake SSN (`123-45-6789`) with explicit doxxing language; assert a 422 response and a row in `removed_posts`.
2. Submit a post where a user shares their own phone number in a casual context; assert the AI score is < 0.4 and status is `published`.
3. Submit a borderline post and verify a row appears in D1 with `status = 'held'` and a message lands in the review queue.
4. Trigger the cron handler manually and confirm the `transparency_daily` table is populated.

## Related
- [`harassment-pattern-detection-durable-objects.md`](harassment-pattern-detection-durable-objects.md)
- `gdpr-article-22-automated-decisions.md`
- [`anonymous-content-reporting-worker-pipeline.md`](anonymous-content-reporting-worker-pipeline.md)
- [`platform-audit-log-immutable-d1-workers.md`](platform-audit-log-immutable-d1-workers.md)

## Sources
- GDPR Article 9 — processing of special categories of personal data
- EU DSA Articles 15, 24 — transparency reporting obligations
- Cloudflare Workers AI — `@cf/meta/llama-3.1-8b-instruct`
- NIST SP 800-188 — De-identifying government datasets (PII pattern reference)
