# Duplicate Issue Detection Using Workers AI Embeddings + Vectorize

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

High-volume repositories accumulate duplicate issue reports — the same bug filed by multiple users with different wording. Manually triaging duplicates costs maintainer time and confuses users who never see their issue resolved. You need an automated system that detects probable duplicates at creation time, ranks candidates by similarity, and posts a comment suggesting existing issues to the reporter.

## Context

When a new issue is opened, a Cloudflare Worker embeds its title and body using Workers AI (`@cf/baai/bge-base-en-v1.5`), queries a Vectorize index for the nearest neighbours, and — if similarity exceeds a configurable threshold — posts a comment via the GitHub API listing the top candidates. The Vectorize index is also updated with the new issue vector so future issues can match against it.

Key design decisions:
- Embed `title + "\n" + body` (truncated to 512 tokens). Title alone gives poor recall; full body is noisy.
- Cosine similarity threshold of `0.85` balances precision and recall for typical issue text. Tune per repo.
- Only issues open for fewer than 90 days are candidates (stale issues are irrelevant).
- False positives (wrong duplicate suggestions) are more tolerable than false negatives; err on the side of suggesting.

## Solution

### 1. Wrangler configuration

```toml
# wrangler.toml
name = "issue-dedup"
main = "src/index.ts"
compatibility_date = "2024-09-23"

[ai]
binding = "AI"

[[vectorize]]
binding = "VECTOR_INDEX"
index_name = "issue-dedup-index"

[vars]
GITHUB_APP_ID = "123456"
DUPLICATE_THRESHOLD = "0.85"
MAX_CANDIDATES = "5"
ISSUE_STALE_DAYS = "90"

# Secrets (set via wrangler secret put)
# GITHUB_APP_PRIVATE_KEY
# GITHUB_INSTALLATION_ID
```

```bash
# Create the Vectorize index
npx wrangler vectorize create issue-dedup-index \
  --dimensions 768 \
  --metric cosine
```

### 2. Types

```typescript
// src/types.ts
export interface Env {
  AI: Ai;
  VECTOR_INDEX: VectorizeIndex;
  GITHUB_APP_ID: string;
  GITHUB_APP_PRIVATE_KEY: string;
  GITHUB_INSTALLATION_ID: string;
  DUPLICATE_THRESHOLD: string;
  MAX_CANDIDATES: string;
  ISSUE_STALE_DAYS: string;
}

export type VectorMetadata = {
  issueNumber: number;
  repoFullName: string;
  title: string;
  htmlUrl: string;
  createdAt: string;
};

export type DuplicateCandidate = VectorMetadata & {
  score: number;
};
```

### 3. Text embedding

```typescript
// src/embed.ts
import type { Env } from "./types";

const MAX_CHARS = 2000; // ~512 tokens for bge-base-en-v1.5

export function buildIssueText(title: string, body: string | null): string {
  const combined = `${title}\n${body ?? ""}`.slice(0, MAX_CHARS).trim();
  return combined;
}

export async function embedText(env: Env, text: string): Promise<number[]> {
  const result = await env.AI.run("@cf/baai/bge-base-en-v1.5", {
    text: [text],
  });
  // result.data is an array of embedding arrays, one per input string
  return result.data[0];
}
```

### 4. Vectorize query and insert

```typescript
// src/vectorize.ts
import type { Env, VectorMetadata, DuplicateCandidate } from "./types";

export async function findSimilarIssues(
  env: Env,
  vector: number[],
  currentIssueNumber: number
): Promise<DuplicateCandidate[]> {
  const threshold = parseFloat(env.DUPLICATE_THRESHOLD);
  const topK = parseInt(env.MAX_CANDIDATES) + 1; // +1 because the issue itself may already be indexed
  const staleCutoff = new Date(
    Date.now() - parseInt(env.ISSUE_STALE_DAYS) * 86_400_000
  ).toISOString();

  const result = await env.VECTOR_INDEX.query(vector, {
    topK,
    returnMetadata: "all",
    filter: {
      // Only match vectors created within the staleness window
      // Note: Vectorize metadata filters use equality/range operators
      createdAt: { $gt: staleCutoff },
    },
  });

  return (
    result.matches
      .filter(
        (m) =>
          m.score >= threshold &&
          (m.metadata as VectorMetadata).issueNumber !== currentIssueNumber
      )
      .slice(0, parseInt(env.MAX_CANDIDATES))
      .map((m) => ({
        ...(m.metadata as VectorMetadata),
        score: m.score,
      }))
  );
}

export async function upsertIssueVector(
  env: Env,
  repoFullName: string,
  issueNumber: number,
  title: string,
  htmlUrl: string,
  createdAt: string,
  vector: number[]
): Promise<void> {
  const id = `${repoFullName.replace("/", "__")}__${issueNumber}`;
  const metadata: VectorMetadata = {
    issueNumber,
    repoFullName,
    title,
    htmlUrl,
    createdAt,
  };

  await env.VECTOR_INDEX.upsert([{ id, values: vector, metadata }]);
}
```

### 5. GitHub App JWT and API helper

```typescript
// src/github.ts
import type { Env } from "./types";

// Minimal JWT for GitHub App — uses RS256
async function createJwt(appId: string, privateKeyPem: string): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = { iat: now - 60, exp: now + 600, iss: appId };

  const encode = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");

  const headerB64 = encode(header);
  const payloadB64 = encode(payload);
  const signingInput = `${headerB64}.${payloadB64}`;

  // Import PEM private key
  const pemBody = privateKeyPem
    .replace(/<redacted-private-key>/g, "")
    .replace(/\s/g, "");
  const der = Uint8Array.from(atob(pemBody), (c) => c.charCodeAt(0));
  const key = await crypto.subtle.importKey(
    "pkcs8",
    der,
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const sig = await crypto.subtle.sign("RSASSA-PKCS1-v1_5", key, new TextEncoder().encode(signingInput));
  const sigB64 = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");

  return `${signingInput}.${sigB64}`;
}

async function getInstallationToken(env: Env): Promise<string> {
  const jwt = await createJwt(env.GITHUB_APP_ID, env.GITHUB_APP_PRIVATE_KEY);
  const res = await fetch(
    `https://api.github.com/app/installations/${env.GITHUB_INSTALLATION_ID}/access_tokens`,
    { method: "POST", headers: { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json" } }
  );
  if (!res.ok) throw new Error(`Token fetch failed: ${res.status}`);
  const data = await res.json<{ token: string }>();
  return data.token;
}

export async function postDuplicateComment(
  env: Env,
  repoFullName: string,
  issueNumber: number,
  candidates: Array<{ issueNumber: number; title: string; htmlUrl: string; score: number }>
): Promise<void> {
  const token = await getInstallationToken(env);
  const lines = candidates.map(
    (c) => `- #${c.issueNumber} — ${c.title} (similarity: ${(c.score * 100).toFixed(1)}%)`
  );
  const body = [
    "**Possible duplicate issues detected** (automated check):",
    "",
    ...lines,
    "",
    "If one of these already tracks your problem, please add a 👍 reaction there instead of continuing here. A maintainer will confirm if this is a duplicate.",
  ].join("\n");

  const [owner, repo] = repoFullName.split("/");
  const res = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/comments`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ body }),
    }
  );
  if (!res.ok) throw new Error(`Comment post failed: ${res.status} ${await res.text()}`);
}
```

### 6. Main handler (queue consumer)

```typescript
// src/index.ts
import type { Env } from "./types";
import { buildIssueText, embedText } from "./embed";
import { findSimilarIssues, upsertIssueVector } from "./vectorize";
import { postDuplicateComment } from "./github";
import type { IssueQueueMessage } from "./router-types";

export default {
  async queue(batch: MessageBatch<IssueQueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { payload } = msg.body;
      if (payload.action !== "opened") { msg.ack(); continue; }

      const { issue, repository } = payload;
      try {
        const text = buildIssueText(issue.title, issue.body);
        const vector = await embedText(env, text);

        // Find duplicates BEFORE inserting so we don't self-match
        const candidates = await findSimilarIssues(env, vector, issue.number);

        // Always upsert — even if no duplicate found, this issue becomes a future candidate
        await upsertIssueVector(
          env,
          repository.full_name,
          issue.number,
          issue.title,
          issue.html_url,
          issue.created_at,
          vector
        );

        if (candidates.length > 0) {
          await postDuplicateComment(env, repository.full_name, issue.number, candidates);
          console.log(
            `Posted duplicate suggestions for ${repository.full_name}#${issue.number}: ` +
            candidates.map((c) => `#${c.issueNumber}`).join(", ")
          );
        }

        msg.ack();
      } catch (err) {
        console.error(`Dedup failed for ${repository.full_name}#${issue.number}:`, err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Implementation Details

**Embedding model selection:**
`@cf/baai/bge-base-en-v1.5` produces 768-dimensional vectors and runs on CPU in Workers AI with no cold-start cost. It outperforms smaller models on code-adjacent English text (error messages, stack traces in issue bodies).

**Threshold tuning:**
- Below 0.80: too many false positives, especially for issues sharing only boilerplate template text.
- Above 0.92: misses paraphrased duplicates.
- 0.85–0.88 is the practical sweet spot for most software repos. Tune per repo by sampling known duplicate pairs from historical data.

**Vectorize metadata filtering:**
Vectorize supports filtering on metadata fields with `$eq`, `$ne`, `$lt`, `$lte`, `$gt`, `$gte`. The `createdAt` filter keeps candidates fresh and reduces index scan cost over time.

**Upsert before or after query?**
Query first, then upsert. Querying before upsert prevents the new issue from matching itself (since Vectorize may serve the freshly inserted vector in a tight timing window).

## Anti-patterns

- **Do not embed only the title.** Titles are often too short and generic ("App crashes", "TypeError") to produce meaningful embeddings.
- **Do not store vectors without metadata.** Without `issueNumber`/`repoFullName` in metadata, matches require a secondary D1 lookup to resolve issue details.
- **Do not call Workers AI synchronously in the webhook handler.** AI inference takes 200–800 ms. Always do it in a queue consumer.
- **Do not post a duplicate comment if the issue is already labeled `duplicate`.** Check labels before posting to avoid spamming re-opened duplicates.
- **Do not set the threshold too low.** A flood of duplicate comments from a bot erodes author trust and increases noise.

## Gotchas

- Workers AI `@cf/baai/bge-base-en-v1.5` truncates inputs at the model's token limit (512 tokens). Inputs exceeding this are silently truncated, not errored. The `MAX_CHARS = 2000` guard in `embed.ts` is a rough approximation; actual tokenisation differs.
- Vectorize indexes are eventually consistent. A newly upserted vector may not be immediately queryable (typically sub-second, but not zero).
- The GitHub App private key must be stored as a Worker secret in PEM format. Newlines in PEM must be preserved — store verbatim, not base64-re-encoded.
- GitHub installation access tokens expire after 1 hour. For high-throughput scenarios, cache the token in KV with a `expirationTtl` of 3300 seconds (55 minutes) to avoid fetching a new one for every comment.
- Vectorize has a 5 MB upsert body limit per batch call. Batching many upserts at once is fine; single-vector upserts are always safe.

## Verification

```bash
# Deploy
npx wrangler deploy

# Check Vectorize index stats
npx wrangler vectorize info issue-dedup-index

# Query index directly with a test vector (use wrangler vectorize query)
# Or open an issue in the target repo and verify the bot comment appears within ~30 seconds

# Tail Worker logs
npx wrangler tail --format pretty
```

## Related

- `workers-github-issue-webhook-router.md` — upstream event source
- `workers-issue-template-enforcement.md` — companion bot on the same opened event

## Sources

- https://developers.cloudflare.com/vectorize/
- https://developers.cloudflare.com/workers-ai/models/bge-base-en-v1.5/
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app
- https://developers.cloudflare.com/vectorize/reference/metadata-filtering/
