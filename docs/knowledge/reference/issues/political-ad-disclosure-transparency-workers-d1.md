# Political Ad Disclosure and Transparency — Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Anonymous accounts on example project post content that functions as political advertising — endorsing
candidates, promoting ballot measures, calling for votes — without any disclosure that the content
is paid-for or sponsored. In jurisdictions with political ad disclosure laws, the platform is
required to: (a) detect that the content is political advertising, (b) require or enforce
disclosure, and (c) maintain a public ad archive for a defined period post-election.

Because example project accounts are anonymous, the ordinary "sponsored by" label workflow used by
Meta or Google does not translate directly: there is no verified identity to attach. However,
content that reads as political advertising still carries disclosure obligations.

---

## Context

Relevant legal frameworks:

- **EU DSA Art. 26** — political advertising must be clearly labelled with the identity of the
  sponsor, the amount spent, and the target audience parameters.
- **EU Political Advertising Regulation (PAR) 2024/900** — came into force October 2025; requires
  publishers of political ads to maintain a transparency register.
- **US FEC 52 U.S.C. § 30120** — "paid for by" disclaimer on public political communications.
- **UK PPERA 2000** — election material imprint requirements.
- **California SB 1339 (2026 cycle)** — AI-generated political ad disclosure requirements.

On example project, the pipeline must:
1. Detect posts that constitute political advertising (Workers AI classifier).
2. If detected and the account has not voluntarily provided disclosure metadata, either hold the
   post for disclosure completion or apply an automated "unverified political ad" label.
3. Archive flagged content in a publicly queryable D1 table (PAR compliance).

---

## Architecture

```
Post → Worker (political-ad-classify → disclosure check → gate)
     → D1 (political_ad_events, political_ad_archive)
     → KV (disclosure_tokens — per-post ephemeral disclosure forms)
     → Queues (disclosure-completion-queue, archive-publish-queue)
```

---

## Implementation

### 1. Political Ad Classifier

```typescript
// src/scoring/political-ad.ts
import type { Env } from '../types';

export interface PoliticalAdScore {
  isPoliticalAd: boolean;
  confidence: number;
  electionCycle: string | null;  // e.g. "EU-2026", "US-2026-midterm"
  adType: 'candidate_endorsement' | 'ballot_measure' | 'issue_advocacy' | 'voter_suppression' | 'none';
  targetJurisdiction: string | null;  // e.g. "DE", "US-CA"
}

const POLITICAL_AD_PROMPT = (content: string) => `
You are a political content classifier for a platform with legal disclosure obligations.

Post content: """${content}"""

Determine if this post constitutes political advertising: content that explicitly or implicitly
promotes a candidate, party, ballot measure, or political position in the context of an electoral
or legislative campaign.

Exclude: general political opinion, news commentary, satire clearly labelled as such.
Include: "vote for X", "support Measure Y", "don't vote for Z", candidate fundraising solicitations,
partisan get-out-the-vote drives targeted at specific groups.

Respond ONLY with JSON:
{
  "is_political_ad": <boolean>,
  "confidence": <0.0–1.0>,
  "election_cycle": <string|null>,
  "ad_type": <"candidate_endorsement"|"ballot_measure"|"issue_advocacy"|"voter_suppression"|"none">,
  "target_jurisdiction": <ISO-3166 country or country-region code|null>
}
`.trim();

export async function classifyPoliticalAd(
  content: string,
  env: Env,
): Promise<PoliticalAdScore> {
  const result = await env.AI.run('@cf/meta/llama-3.3-70b-instruct-fp8-fast', {
    prompt: POLITICAL_AD_PROMPT(content),
    max_tokens: 200,
  });

  try {
    const parsed = JSON.parse((result as { response: string }).response);
    return {
      isPoliticalAd:     Boolean(parsed.is_political_ad),
      confidence:        Number(parsed.confidence ?? 0),
      electionCycle:     parsed.election_cycle ?? null,
      adType:            parsed.ad_type ?? 'none',
      targetJurisdiction: parsed.target_jurisdiction ?? null,
    };
  } catch {
    return {
      isPoliticalAd: false,
      confidence: 0,
      electionCycle: null,
      adType: 'none',
      targetJurisdiction: null,
    };
  }
}
```

### 2. Disclosure Check — KV-Backed Ephemeral Token

```typescript
// src/disclosure/check.ts
import type { Env } from '../types';

export interface DisclosureStatus {
  provided: boolean;
  sponsorLabel: string | null;    // e.g. "Citizens for X PAC"
  paidFor: boolean;
  amount: number | null;          // reported spend in USD cents
  submittedAt: number | null;
}

export async function getDisclosureStatus(
  postId: string,
  env: Env,
): Promise<DisclosureStatus> {
  const stored = await env.DISCLOSURE_KV.get<DisclosureStatus>(
    `disclosure:${postId}`,
    'json',
  );
  if (!stored) {
    return { provided: false, sponsorLabel: null, paidFor: false, amount: null, submittedAt: null };
  }
  return stored;
}

export async function storeDisclosure(
  postId: string,
  disclosure: Omit<DisclosureStatus, 'provided' | 'submittedAt'>,
  env: Env,
): Promise<void> {
  const value: DisclosureStatus = {
    ...disclosure,
    provided: true,
    submittedAt: Date.now(),
  };
  // TTL: keep for 2 years (PAR requires 1 year post-election; 2 years is safe)
  await env.DISCLOSURE_KV.put(
    `disclosure:${postId}`,
    JSON.stringify(value),
    { expirationTtl: 63_072_000 }, // 2 years in seconds
  );
}
```

### 3. Post Gate Handler

```typescript
// src/handlers/political-ad-gate.ts
import { classifyPoliticalAd } from '../scoring/political-ad';
import { getDisclosureStatus } from '../disclosure/check';
import type { Env } from '../types';

const CONFIDENCE_THRESHOLD = 0.70;

export async function handlePostWithAdGate(
  request: Request,
  env: Env,
): Promise<Response> {
  const body = await request.json<{
    postId: string;
    content: string;
    disclosureToken?: string;    // optional: pre-submitted disclosure reference
  }>();

  const classification = await classifyPoliticalAd(body.content, env);

  if (!classification.isPoliticalAd || classification.confidence < CONFIDENCE_THRESHOLD) {
    // Not political advertising — proceed normally
    return Response.json({ postId: body.postId, status: 'accepted' });
  }

  // Check if the user already submitted a disclosure for this post
  const disclosure = body.disclosureToken
    ? await getDisclosureStatus(body.disclosureToken, env)
    : { provided: false, sponsorLabel: null, paidFor: false, amount: null, submittedAt: null };

  // Persist the detection event
  await env.DB.prepare(
    `INSERT OR IGNORE INTO political_ad_events
       (post_id, confidence, ad_type, election_cycle, target_jurisdiction,
        disclosure_provided, sponsor_label, paid_for, amount_cents, detected_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, unixepoch())`,
  ).bind(
    body.postId,
    classification.confidence,
    classification.adType,
    classification.electionCycle,
    classification.targetJurisdiction,
    disclosure.provided ? 1 : 0,
    disclosure.sponsorLabel,
    disclosure.paidFor ? 1 : 0,
    disclosure.amount,
  ).run();

  if (!disclosure.provided) {
    // Hold post, return disclosure-required response with a form token
    const formToken = crypto.randomUUID();
    await env.DISCLOSURE_KV.put(
      `pending:${formToken}`,
      JSON.stringify({ postId: body.postId, detectedAt: Date.now() }),
      { expirationTtl: 3600 }, // 1-hour window to complete disclosure
    );

    return Response.json(
      {
        postId: body.postId,
        status: 'disclosure_required',
        formToken,
        message: 'This post has been identified as political advertising. Please complete the disclosure form.',
      },
      { status: 202 },
    );
  }

  // Disclosure provided — publish with label and archive
  await env.ARCHIVE_QUEUE.send({
    postId: body.postId,
    adType: classification.adType,
    electionCycle: classification.electionCycle,
    targetJurisdiction: classification.targetJurisdiction,
    sponsorLabel: disclosure.sponsorLabel,
    paidFor: disclosure.paidFor,
    amountCents: disclosure.amount,
  });

  return Response.json({
    postId: body.postId,
    status: 'accepted_with_disclosure_label',
    label: `Political ad — ${disclosure.sponsorLabel ?? 'unverified sponsor'}`,
  });
}
```

### 4. Archive Consumer — PAR Transparency Register

```typescript
// src/consumers/political-ad-archive.ts
import type { Env } from '../types';

interface ArchiveMessage {
  postId: string;
  adType: string;
  electionCycle: string | null;
  targetJurisdiction: string | null;
  sponsorLabel: string | null;
  paidFor: boolean;
  amountCents: number | null;
}

export async function archivePoliticalAd(
  batch: MessageBatch<ArchiveMessage>,
  env: Env,
): Promise<void> {
  const stmt = env.DB.prepare(
    `INSERT OR IGNORE INTO political_ad_archive
       (post_id, ad_type, election_cycle, target_jurisdiction,
        sponsor_label, paid_for, amount_cents, archived_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, unixepoch())`,
  );

  const dbBatch = batch.messages.map((msg) =>
    stmt.bind(
      msg.body.postId,
      msg.body.adType,
      msg.body.electionCycle,
      msg.body.targetJurisdiction,
      msg.body.sponsorLabel,
      msg.body.paidFor ? 1 : 0,
      msg.body.amountCents,
    ),
  );

  await env.DB.batch(dbBatch);
  batch.messages.forEach((m) => m.ack());
}
```

### 5. D1 Schema

```sql
CREATE TABLE IF NOT EXISTS political_ad_events (
  post_id               TEXT PRIMARY KEY,
  confidence            REAL NOT NULL,
  ad_type               TEXT NOT NULL,
  election_cycle        TEXT,
  target_jurisdiction   TEXT,
  disclosure_provided   INTEGER NOT NULL DEFAULT 0,
  sponsor_label         TEXT,
  paid_for              INTEGER NOT NULL DEFAULT 0,
  amount_cents          INTEGER,
  detected_at           INTEGER NOT NULL,
  final_status          TEXT   -- 'published' | 'rejected' | 'pending_disclosure'
);

-- PAR-compliant public transparency register (read-accessible via API)
CREATE TABLE IF NOT EXISTS political_ad_archive (
  post_id               TEXT PRIMARY KEY,
  ad_type               TEXT NOT NULL,
  election_cycle        TEXT,
  target_jurisdiction   TEXT,
  sponsor_label         TEXT,
  paid_for              INTEGER NOT NULL DEFAULT 0,
  amount_cents          INTEGER,
  archived_at           INTEGER NOT NULL
);

CREATE INDEX idx_pad_archive_cycle ON political_ad_archive(election_cycle, archived_at DESC);
CREATE INDEX idx_pad_archive_jurisdiction ON political_ad_archive(target_jurisdiction, archived_at DESC);
```

### 6. Public Transparency API Endpoint

```typescript
// src/handlers/ad-transparency.ts
import type { Env } from '../types';

export async function handleTransparencyQuery(
  request: Request,
  env: Env,
): Promise<Response> {
  const url = new URL(request.url);
  const jurisdiction = url.searchParams.get('jurisdiction') ?? '%';
  const cycle        = url.searchParams.get('election_cycle') ?? '%';
  const page         = Number(url.searchParams.get('page') ?? 1);
  const pageSize     = 50;
  const offset       = (page - 1) * pageSize;

  const rows = await env.DB.prepare(
    `SELECT post_id, ad_type, election_cycle, target_jurisdiction,
            sponsor_label, paid_for, amount_cents,
            datetime(archived_at, 'unixepoch') AS archived_at
     FROM political_ad_archive
     WHERE (target_jurisdiction LIKE ? OR ? = '%')
       AND (election_cycle LIKE ? OR ? = '%')
     ORDER BY archived_at DESC
     LIMIT ? OFFSET ?`,
  ).bind(jurisdiction, jurisdiction, cycle, cycle, pageSize, offset)
   .all();

  return Response.json({
    page,
    results: rows.results,
  }, {
    headers: { 'Cache-Control': 'public, max-age=300' },
  });
}
```

---

## Anti-patterns

- **Blocking all posts that mention a politician's name** — election commentary, journalism, and
  satire are not political advertising. The classifier must distinguish advocacy/endorsement from
  commentary; require ≥ 0.70 confidence before triggering the disclosure gate.
- **Accepting self-reported disclosures without any verification** — anonymous platforms cannot
  verify sponsor identity, but they can verify that a disclosure was submitted and log the
  submission timestamp; that log is the platform's due-diligence record.
- **Deleting non-disclosed political ads without archiving** — PAR Art. 12 requires that content
  removed for non-disclosure is still retained in the transparency register for 1 year.
- **Exposing the classifier score in the API response** — it teaches operators how to rewrite
  ads to score below threshold.

---

## Gotchas

- `DISCLOSURE_KV` TTL must cover the full statutory retention period (PAR: 1 year post-election
  date). Use D1 `political_ad_archive` for long-term storage; KV is only for the short-lived
  pending-disclosure flow.
- The classifier may over-trigger near election dates when organic political content spikes.
  Consider adding a `CONFIDENCE_THRESHOLD` bump to 0.80 outside official campaign windows.
- EU PAR Art. 7 requires disclosure of the "estimated amount or value" of political advertising.
  For anonymous platforms where spend is not known, the disclosure form should include a
  self-reported field AND a platform disclaimer that amounts are unverified.
- Worker CPU limits apply: chaining AI inference + D1 writes + KV operations in a single
  synchronous handler can approach 50 ms CPU. Profile under load; consider deferring the archive
  write to a Queue consumer.

---

## Verification

```sql
-- Political ads detected by jurisdiction this week
SELECT target_jurisdiction, ad_type,
       COUNT(*) AS detected,
       SUM(disclosure_provided) AS disclosures_provided
FROM political_ad_events
WHERE detected_at > unixepoch() - 604800
GROUP BY target_jurisdiction, ad_type
ORDER BY detected DESC;

-- PAR archive coverage: ads archived vs. ads detected
SELECT
  COUNT(*) AS total_detected,
  (SELECT COUNT(*) FROM political_ad_archive
   WHERE archived_at > unixepoch() - 604800) AS total_archived
FROM political_ad_events
WHERE detected_at > unixepoch() - 604800;
```

---

## Related

- `election-misinformation-detection-workers-ai.md` — false election claims (separate from ads)
- `dark-patterns-deceptive-design-regulation.md` — deceptive UX regulation context
- `digital-services-act-platform-compliance.md` — DSA compliance overview
- `platform-audit-log-immutable-d1-workers.md` — tamper-proof audit logging
- `automated-content-policy-rule-engine-workers-d1.md` — policy rule engine integration

---

## Sources

- EU Political Advertising Regulation (EU) 2024/900: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202400900
- DSA Art. 26 — Online advertising transparency obligations
- FEC 52 U.S.C. § 30120 — Disclaimer requirements for political advertisements
- UK PPERA 2000 — Political Parties, Elections and Referendums Act
- California SB 1339 (2026) — AI-generated political content disclosure
- Cloudflare Workers KV: https://developers.cloudflare.com/kv/
