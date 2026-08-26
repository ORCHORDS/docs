# Election Misinformation Detection with Workers AI

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

During electoral periods example project sees surges in posts containing false claims about voting procedures, candidate eligibility, and election results. These posts are distinct from general misinformation because they are time-sensitive (stale after election day), jurisdiction-specific, and carry elevated regulatory risk under the EU DSA Article 34 systemic risk assessment for electoral integrity.

## Context

Election misinformation on anonymous social platforms is particularly dangerous because anonymity removes personal accountability and allows coordinated false narratives to propagate without attribution. example project must comply with the EU DSA's requirement for Very Large Online Platforms to conduct risk assessments and implement mitigations specifically for elections. The pipeline here uses Cloudflare Workers AI to score posts against an election-claim taxonomy, cross-references claims against a D1 fact-check index that is updated from authoritative electoral commission sources, and applies a tiered response: soft label, reach restriction, or removal. An active election calendar stored in D1 controls when the heightened scoring path is engaged.

## Election Calendar and Claim Taxonomy

An `elections` table in D1 defines active electoral periods by jurisdiction. The ingestion Worker checks this table before engaging the expensive AI scoring path, ensuring that heightened scrutiny applies only when and where relevant.

```typescript
export interface Env {
  AI: Ai;
  DB: D1Database;
}

interface ElectionPeriod {
  jurisdiction_code: string; // ISO 3166-1 alpha-2, e.g. 'US', 'DE', 'FR'
  election_name: string;
  start_date: string;        // ISO 8601
  end_date: string;
  heightened_from: string;   // days before election start when heightened mode begins
}

type ElectionClaimCategory =
  | 'NONE'
  | 'PROCEDURAL_FALSEHOOD'   // wrong voting dates, locations, ID requirements
  | 'CANDIDATE_FALSEHOOD'    // false eligibility or criminal claims
  | 'RESULT_DISPUTE'         // false outcome claims
  | 'SUPPRESSION_NARRATIVE'  // discouraging voting via false consequences
  | 'AUTHENTIC_CONCERN';     // legitimate political speech — do not suppress

interface ClaimScore {
  category: ElectionClaimCategory;
  confidence: number;
  jurisdictionHint: string | null;
  claimSummary: string;
}

async function getActiveElection(
  db: D1Database,
  today: string,
): Promise<ElectionPeriod | null> {
  return db
    .prepare(
      `SELECT * FROM elections
       WHERE heightened_from <= ?1 AND end_date >= ?1
       ORDER BY start_date ASC LIMIT 1`,
    )
    .bind(today)
    .first<ElectionPeriod>();
}
```

## Workers AI Claim Classification

When an active election period is detected, the post is evaluated with a structured prompt that explicitly names the election and jurisdiction to improve classification accuracy. The model is asked to extract the implicit jurisdiction from the text as well, which allows cross-checking against the active election record.

```typescript
function buildElectionPrompt(election: ElectionPeriod): string {
  return `You are an election integrity content classifier.
Current active election: ${election.election_name} (${election.jurisdiction_code}), ending ${election.end_date}.

Classify the user post into one of:
- NONE: no election content
- PROCEDURAL_FALSEHOOD: false claims about how, when, or where to vote
- CANDIDATE_FALSEHOOD: false claims about a candidate's eligibility, record, or identity
- RESULT_DISPUTE: false claims about election outcomes or fraud without evidence
- SUPPRESSION_NARRATIVE: false claims intended to discourage eligible voters
- AUTHENTIC_CONCERN: legitimate political speech, opinion, or verified criticism

Return ONLY JSON: {"category":"<CATEGORY>","confidence":0.0-1.0,"jurisdictionHint":"<2-letter code or null>","claimSummary":"<15 words max>"}`;
}

async function classifyElectionPost(
  ai: Ai,
  text: string,
  election: ElectionPeriod,
): Promise<ClaimScore> {
  const result = await ai.run('@cf/meta/llama-3.1-8b-instruct', {
    messages: [
      { role: 'system', content: buildElectionPrompt(election) },
      { role: 'user', content: text },
    ],
    max_tokens: 150,
    temperature: 0,
  }) as { response: string };

  try {
    return JSON.parse(result.response.trim()) as ClaimScore;
  } catch {
    return {
      category: 'NONE',
      confidence: 0,
      jurisdictionHint: null,
      claimSummary: '',
    };
  }
}
```

## Fact-Check Index Lookup and Tiered Response

Classified claims are cross-referenced against a `fact_checks` table populated by a daily sync from official electoral commission sources. If a stored denial of the claim exists, confidence is boosted and the harder action tier is applied. Posts labelled `AUTHENTIC_CONCERN` bypass all suppression regardless of score.

```typescript
interface FactCheck {
  claim_pattern: string;  // simplified key phrase
  verdict: 'FALSE' | 'MISLEADING' | 'DISPUTED';
  source_url: string;
}

async function lookupFactCheck(
  db: D1Database,
  claimSummary: string,
  jurisdictionCode: string,
): Promise<FactCheck | null> {
  // Simplified substring match — production would use FTS5 or vector search
  return db
    .prepare(
      `SELECT claim_pattern, verdict, source_url FROM fact_checks
       WHERE jurisdiction_code = ?1
         AND ?2 LIKE '%' || claim_pattern || '%'
       LIMIT 1`,
    )
    .bind(jurisdictionCode, claimSummary.toLowerCase())
    .first<FactCheck>();
}

type ModerationAction = 'ALLOW' | 'LABEL' | 'RESTRICT_REACH' | 'REMOVE';

function determineAction(
  score: ClaimScore,
  factCheck: FactCheck | null,
): ModerationAction {
  if (score.category === 'NONE' || score.category === 'AUTHENTIC_CONCERN') {
    return 'ALLOW';
  }

  // Boost effective confidence when a matching fact-check exists
  const effectiveConfidence = factCheck
    ? Math.min(score.confidence + 0.2, 1.0)
    : score.confidence;

  if (score.category === 'SUPPRESSION_NARRATIVE' || score.category === 'PROCEDURAL_FALSEHOOD') {
    if (effectiveConfidence >= 0.75) return 'REMOVE';
    if (effectiveConfidence >= 0.5)  return 'RESTRICT_REACH';
  }

  if (effectiveConfidence >= 0.6) return 'LABEL';
  return 'ALLOW';
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { text, postId, sessionToken, countryCode } =
      await request.json<{
        text: string;
        postId: string;
        sessionToken: string;
        countryCode: string;
      }>();

    const today = new Date().toISOString().slice(0, 10);
    const election = await getActiveElection(env.DB, today);

    // Outside election window: skip expensive AI path
    if (!election) {
      return Response.json({ action: 'ALLOW', electionMode: false });
    }

    const claimScore = await classifyElectionPost(env.AI, text, election);

    let factCheck: FactCheck | null = null;
    if (claimScore.category !== 'NONE' && claimScore.category !== 'AUTHENTIC_CONCERN') {
      const jurisdiction = claimScore.jurisdictionHint ?? countryCode;
      factCheck = await lookupFactCheck(env.DB, claimScore.claimSummary, jurisdiction);
    }

    const action = determineAction(claimScore, factCheck);

    // Audit record
    await env.DB.prepare(
      `INSERT INTO election_moderation_log
         (post_id, session_token, election_id, category, confidence, fact_check_verdict, action, created_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`,
    )
      .bind(
        postId,
        sessionToken,
        election.election_name,
        claimScore.category,
        claimScore.confidence,
        factCheck?.verdict ?? null,
        action,
        new Date().toISOString(),
      )
      .run();

    return Response.json({
      action,
      electionMode: true,
      electionName: election.election_name,
      factCheckSource: factCheck?.source_url ?? null,
    });
  },
} satisfies ExportedHandler<Env>;
```

## D1 Schema

```sql
-- migration: 0010_election_moderation.sql

CREATE TABLE IF NOT EXISTS elections (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  jurisdiction_code TEXT NOT NULL,
  election_name     TEXT NOT NULL,
  start_date        TEXT NOT NULL,
  end_date          TEXT NOT NULL,
  heightened_from   TEXT NOT NULL  -- date from which heightened mode activates
);

CREATE TABLE IF NOT EXISTS fact_checks (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  jurisdiction_code TEXT NOT NULL,
  claim_pattern     TEXT NOT NULL,
  verdict           TEXT NOT NULL CHECK(verdict IN ('FALSE','MISLEADING','DISPUTED')),
  source_url        TEXT NOT NULL,
  synced_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS election_moderation_log (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  post_id             TEXT NOT NULL,
  session_token       TEXT NOT NULL,
  election_id         TEXT NOT NULL,
  category            TEXT NOT NULL,
  confidence          REAL NOT NULL,
  fact_check_verdict  TEXT,
  action              TEXT NOT NULL CHECK(action IN ('ALLOW','LABEL','RESTRICT_REACH','REMOVE')),
  created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_election_log_action
  ON election_moderation_log(action, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_fact_checks_jurisdiction
  ON fact_checks(jurisdiction_code, claim_pattern);
```

## Anti-patterns

- Running the election misinformation pipeline on all posts year-round; the election calendar gate ensures classifier resources are spent only when elections are active and reduces false-positive rates outside of electoral periods.
- Suppressing `AUTHENTIC_CONCERN` posts; legitimate political criticism of candidates or election administration must never be removed by automated systems — only courts and regulators can compel that.
- Treating the LLM confidence score alone as sufficient for a REMOVE action; always require either a fact-check table hit or a confidence above 0.85 before removal, and route borderline cases to human review.

## Gotchas

- `LIKE '%' || claim_pattern || '%'` in SQLite performs a full-table scan; for production fact-check lookup, enable FTS5 in D1 and use `MATCH` queries, or maintain a KV index keyed by normalized claim hash.
- Election periods overlap across jurisdictions simultaneously (e.g., a US midterm overlapping a German state election); `getActiveElection` returns only the most imminent — extend to return all active elections and run classification per jurisdiction if your user base spans multiple active electoral contexts.

## Verification

```bash
# Seed an active election in D1
wrangler d1 execute example project-db \
  --command "INSERT INTO elections (jurisdiction_code, election_name, start_date, end_date, heightened_from) VALUES ('US','US Midterms 2026','2026-11-03','2026-11-04','2026-10-04')"

# Test with a suppression narrative post
curl -X POST https://example project-ingest.example.workers.dev/election \
  -H "Content-Type: application/json" \
  -d '{"text":"They changed the voting day to November 5th, do not show up on the 3rd","postId":"p010","sessionToken":"s_test","countryCode":"US"}'

# Review moderation decisions
wrangler d1 execute example project-db \
  --command "SELECT category, action, confidence, fact_check_verdict, created_at FROM election_moderation_log ORDER BY created_at DESC LIMIT 20"
```

## Related

- `issues/misinformation-labeling-pipeline-ugc.md`
- `issues/coordinated-inauthentic-behavior-detection-d1.md`
- `issues/digital-services-act-platform-compliance.md`
- `issues/platform-audit-log-immutable-d1-workers.md`

## Sources

- https://developers.cloudflare.com/workers-ai/models/llama-3.1-8b-instruct/
- https://developers.cloudflare.com/d1/
- https://digital-strategy.ec.europa.eu/en/policies/digital-services-act-package
- https://www.eac.gov/election-officials/election-security
