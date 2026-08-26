# Translation Crowdsourcing Pipeline with D1 and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A multilingual platform wants community contributors to submit, vote on, and approve
translations for missing or low-quality strings, similar to Mozilla Pontoon or
Transifex's community feature. You need a lightweight crowdsourcing pipeline on the
Cloudflare stack: contributors submit proposals via a Workers API, proposals are stored
in D1, voting is tracked, approved translations are promoted to KV (the live translation
store), and stale auto-translated strings are queued for human review via Workers Queues.

## Context

This pipeline has four actors: **source strings** (canonical English in D1),
**proposals** (community-submitted translations in D1), **votes** (upvotes/downvotes in
D1), and the **live KV store** (serving translation lookups). Promotion from proposal to
live happens automatically once a quorum is reached, or manually by a locale maintainer.
Workers Queues handles async promotion and reviewer notification.

Applicable stack: Workers, D1, KV, Workers Queues, optional Workers AI (quality gate).

---

## 1. D1 Schema

```sql
-- migration 001_crowdsource.sql

CREATE TABLE source_strings (
  id          TEXT PRIMARY KEY,       -- e.g. "button.submit"
  namespace   TEXT NOT NULL,
  source_text TEXT NOT NULL,          -- canonical English
  context     TEXT,                   -- translator notes
  created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE translation_proposals (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  string_id     TEXT NOT NULL REFERENCES source_strings(id),
  locale        TEXT NOT NULL,
  proposed_text TEXT NOT NULL,
  contributor   TEXT NOT NULL,        -- user ID (hashed)
  status        TEXT NOT NULL DEFAULT 'pending',
  -- 'pending' | 'approved' | 'rejected' | 'superseded'
  vote_score    INTEGER NOT NULL DEFAULT 0,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at   TEXT
);

CREATE TABLE proposal_votes (
  proposal_id INTEGER NOT NULL REFERENCES translation_proposals(id),
  voter       TEXT NOT NULL,          -- user ID (hashed)
  value       INTEGER NOT NULL,       -- +1 or -1
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (proposal_id, voter)
);

CREATE INDEX idx_proposals_string_locale
  ON translation_proposals (string_id, locale, status, vote_score DESC);

CREATE INDEX idx_proposals_contributor
  ON translation_proposals (contributor, status);
```

---

## 2. Submitting a Proposal

```typescript
// src/routes/proposals.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ProposalInput {
  stringId: string;
  locale: string;
  proposedText: string;
  contributorId: string;
}

const MIN_TEXT_LENGTH = 1;
const MAX_TEXT_LENGTH = 2000;

export async function submitProposal(
  db: D1Database,
  input: ProposalInput,
): Promise<{ proposalId: number }> {
  const { stringId, locale, proposedText, contributorId } = input;

  if (!proposedText.trim().length || proposedText.length > MAX_TEXT_LENGTH) {
    throw new RangeError(`Proposed text must be 1–${MAX_TEXT_LENGTH} chars`);
  }

  // Validate BCP 47 locale tag
  try {
    new Intl.Locale(locale);
  } catch {
    throw new TypeError(`Invalid locale: ${locale}`);
  }

  // Check source string exists
  const source = await db
    .prepare('SELECT id FROM source_strings WHERE id = ? LIMIT 1')
    .bind(stringId)
    .first<{ id: string }>();
  if (!source) throw new ReferenceError(`Source string not found: ${stringId}`);

  // Prevent duplicate pending proposals from same contributor
  const existing = await db
    .prepare(
      `SELECT id FROM translation_proposals
       WHERE string_id = ? AND locale = ? AND contributor = ? AND status = 'pending'
       LIMIT 1`,
    )
    .bind(stringId, locale, contributorId)
    .first<{ id: number }>();
  if (existing) throw new Error('Contributor already has a pending proposal for this string');

  const result = await db
    .prepare(
      `INSERT INTO translation_proposals (string_id, locale, proposed_text, contributor)
       VALUES (?, ?, ?, ?)
       RETURNING id`,
    )
    .bind(stringId, locale, proposedText, contributorId)
    .first<{ id: number }>();

  if (!result) throw new Error('Proposal insert failed');
  return { proposalId: result.id };
}
```

---

## 3. Voting and Automatic Quorum Promotion

```typescript
// src/lib/voting.ts
import type { D1Database, KVNamespace, Queue } from '@cloudflare/workers-types';

const QUORUM = 5;           // net upvotes needed for auto-approval
const REJECTION_THRESHOLD = -3; // net downvotes for auto-rejection

export interface PromotionMessage {
  proposalId: number;
  stringId: string;
  locale: string;
  approvedText: string;
}

export async function castVote(
  db: D1Database,
  kv: KVNamespace,
  queue: Queue<PromotionMessage>,
  proposalId: number,
  voterId: string,
  value: 1 | -1,
): Promise<{ newScore: number; promoted: boolean }> {
  // Upsert vote (change of mind allowed)
  await db
    .prepare(
      `INSERT INTO proposal_votes (proposal_id, voter, value)
       VALUES (?, ?, ?)
       ON CONFLICT (proposal_id, voter) DO UPDATE SET value = excluded.value`,
    )
    .bind(proposalId, voterId, value)
    .run();

  // Recompute score from all votes
  const scoreRow = await db
    .prepare(
      `SELECT COALESCE(SUM(value), 0) AS score
       FROM proposal_votes
       WHERE proposal_id = ?`,
    )
    .bind(proposalId)
    .first<{ score: number }>();

  const newScore = scoreRow?.score ?? 0;

  await db
    .prepare('UPDATE translation_proposals SET vote_score = ? WHERE id = ?')
    .bind(newScore, proposalId)
    .run();

  // Auto-approve
  if (newScore >= QUORUM) {
    const proposal = await db
      .prepare(
        `SELECT string_id, locale, proposed_text, status
         FROM translation_proposals WHERE id = ? LIMIT 1`,
      )
      .bind(proposalId)
      .first<{ string_id: string; locale: string; proposed_text: string; status: string }>();

    if (proposal && proposal.status === 'pending') {
      await db
        .prepare(
          `UPDATE translation_proposals
           SET status = 'approved', reviewed_at = datetime('now')
           WHERE id = ?`,
        )
        .bind(proposalId)
        .run();

      // Enqueue promotion to KV
      await queue.send({
        proposalId,
        stringId: proposal.string_id,
        locale: proposal.locale,
        approvedText: proposal.proposed_text,
      });

      return { newScore, promoted: true };
    }
  }

  // Auto-reject
  if (newScore <= REJECTION_THRESHOLD) {
    await db
      .prepare(
        `UPDATE translation_proposals
         SET status = 'rejected', reviewed_at = datetime('now')
         WHERE id = ?`,
      )
      .bind(proposalId)
      .run();
  }

  return { newScore, promoted: false };
}
```

---

## 4. Promotion Consumer: Writing to Live KV

```typescript
// src/consumers/promotion-consumer.ts
import type {
  MessageBatch,
  KVNamespace,
  D1Database,
} from '@cloudflare/workers-types';
import type { PromotionMessage } from '../lib/voting';

export async function handlePromotionBatch(
  batch: MessageBatch<PromotionMessage>,
  kv: KVNamespace,
  db: D1Database,
): Promise<void> {
  for (const message of batch.messages) {
    const { stringId, locale, approvedText } = message.body;

    try {
      // Write to live KV store
      const kvKey = `translations:${locale}:${stringId}`;
      await kv.put(kvKey, approvedText, { expirationTtl: 86400 * 30 });

      // Mark any other pending proposals for this string+locale as superseded
      await db
        .prepare(
          `UPDATE translation_proposals
           SET status = 'superseded'
           WHERE string_id = ? AND locale = ? AND status = 'pending'
             AND id != ?`,
        )
        .bind(stringId, locale, message.body.proposalId)
        .run();

      message.ack();
    } catch (err) {
      console.error('Promotion failed:', err);
      message.retry();
    }
  }
}
```

Workers Queue binding in `wrangler.toml`:

```toml
[[queues.consumers]]
queue = "translation-promotions"
max_batch_size = 20
max_batch_timeout = 5
max_retries = 3

[[queues.producers]]
queue = "translation-promotions"
binding = "PROMOTION_QUEUE"
```

---

## 5. Listing Open Proposals with Vote Counts

```typescript
// src/lib/proposal-listing.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ProposalSummary {
  id: number;
  proposed_text: string;
  vote_score: number;
  contributor: string;
  created_at: string;
}

export async function listOpenProposals(
  db: D1Database,
  stringId: string,
  locale: string,
): Promise<ProposalSummary[]> {
  const rows = await db
    .prepare(
      `SELECT id, proposed_text, vote_score, contributor, created_at
       FROM translation_proposals
       WHERE string_id = ? AND locale = ? AND status = 'pending'
       ORDER BY vote_score DESC, created_at ASC
       LIMIT 50`,
    )
    .bind(stringId, locale)
    .all<ProposalSummary>();

  return rows.results;
}
```

---

## 6. Workers AI Quality Gate Before Promotion

Optionally run a quality check using Workers AI before enqueuing the promotion, to
filter machine-submitted spam or low-quality proposals:

```typescript
// src/lib/quality-gate.ts
import type { Ai } from '@cloudflare/workers-types';

export async function meetsQualityThreshold(
  ai: Ai,
  sourceText: string,
  proposedText: string,
  locale: string,
): Promise<boolean> {
  const prompt = `You are a translation quality reviewer.
Source (English): "${sourceText}"
Proposed translation (${locale}): "${proposedText}"
Does this translation accurately convey the meaning without obvious errors?
Reply with only "yes" or "no".`;

  const response = await ai.run('@cf/meta/llama-3-8b-instruct', {
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 5,
  });

  const answer = (response as { response?: string }).response?.trim().toLowerCase();
  return answer === 'yes';
}
```

---

## Anti-patterns

- **Storing proposed translations directly in KV without D1** — you lose the audit trail,
  version history, and the ability to run aggregate queries (most active contributors,
  approval rates per locale).
- **Allowing unrestricted self-voting** — a contributor who submits a proposal must not
  be able to vote on it. Gate votes with `WHERE contributor != voterId`.
- **Promoting without superseding competing proposals** — leaving old pending proposals
  open after one is approved confuses reviewers and inflates the review queue.
- **Using the same KV namespace for crowdsourced and machine-translated strings** —
  separate namespaces allow you to roll back crowdsourced strings independently.
- **Blocking the Workers AI quality check on the vote path** — AI inference adds 200–
  800 ms latency. Run the quality gate asynchronously via a Queues pre-queue worker.

## Gotchas

- D1's `ON CONFLICT DO UPDATE` requires the conflicting columns to be covered by a
  PRIMARY KEY or UNIQUE constraint. `proposal_votes (proposal_id, voter)` must be a
  composite primary key or unique index.
- Workers Queues delivers messages at-least-once. Promotion writes to KV must be
  idempotent; a duplicate promotion for the same `proposalId` is harmless if you
  `ack()` on success.
- `COALESCE(SUM(value), 0)` returns `null` if there are no rows in SQLite — without
  `COALESCE` the TypeScript `number` typing will silently be `null` at runtime.
- Contributors identified by hashed user IDs can change between sessions. Use a stable
  internal user ID (not a session token) as the contributor column value.
- Workers Queues consumer batches time out after `max_batch_timeout` seconds. Keep
  promotion logic lightweight; defer heavy work (email notifications) to a second queue.

## Verification

```typescript
// test/voting.test.ts
import { castVote } from '../src/lib/voting';

describe('quorum promotion', () => {
  it('promotes proposal after QUORUM upvotes', async () => {
    // Use a D1 in-memory test double or miniflare
    // ...
    for (let i = 0; i < 5; i++) {
      const { promoted } = await castVote(db, kv, queue, proposalId, `voter${i}`, 1);
      if (i < 4) expect(promoted).toBe(false);
      else expect(promoted).toBe(true);
    }
  });
});
```

Inspect D1 state:

```bash
wrangler d1 execute <DB_NAME> --command \
  "SELECT status, COUNT(*) FROM translation_proposals GROUP BY status;"
```

Check KV promotion:

```bash
wrangler kv:key get --namespace-id=<ID> "translations:de:button.submit"
```

## Related

- `workers-queues-async-translation-pipeline.md`
- `translation-kv-caching-ttl-strategy.md`
- `d1-schema-locale-preferences-content-translations-2026.md`
- `machine-translation-workers-ai-quality-scoring.md`
- `crowdin-phrase-translation-pipeline-automation.md`

## Sources

- Cloudflare D1: https://developers.cloudflare.com/d1/
- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Workers AI models: https://developers.cloudflare.com/workers-ai/models/
- Mozilla Pontoon (reference implementation): https://github.com/mozilla/pontoon
