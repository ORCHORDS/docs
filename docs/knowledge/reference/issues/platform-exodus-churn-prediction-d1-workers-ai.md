# Platform Exodus & Churn Prediction — D1 + Workers AI

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

example project occasionally experiences mass user departures ("platform exodus") triggered by a
policy change, a viral controversy, or a competitor launch. By the time the exodus is visible
in DAU metrics, a large fraction of users have already left. This article covers an early-
warning system that detects churn precursors — declining session frequency, reduced post
depth, community disengagement — and uses Workers AI classification to surface at-risk
community clusters before they migrate away.

---

## Context

Anonymous platforms cannot build per-user churn models because there is no persistent
identity across sessions. Instead, churn must be modelled at the **community cluster** level:
a cluster of posts and reactions sharing a topic tag or shard. Cluster-level signals that
precede exodus include:

- Falling posting cadence relative to the cluster's historical baseline.
- Increasing ratio of "farewell" or "I'm leaving" sentiment in posts.
- Declining cross-cluster link sharing (the cluster stops referencing other communities).
- Rising post deletion rate (users removing content before leaving).

D1 stores session and post activity; Workers AI classifies post sentiment; a scheduled Worker
aggregates the signals and emits a risk score per cluster.

---

## Schema

```sql
CREATE TABLE cluster_activity (
  cluster_tag  TEXT NOT NULL,
  day          TEXT NOT NULL,   -- YYYY-MM-DD
  post_count   INTEGER DEFAULT 0,
  delete_count INTEGER DEFAULT 0,
  session_count INTEGER DEFAULT 0,
  PRIMARY KEY (cluster_tag, day)
);

CREATE TABLE churn_risk (
  id           TEXT PRIMARY KEY,
  cluster_tag  TEXT NOT NULL,
  risk_score   REAL NOT NULL,   -- 0..1
  signals      TEXT,            -- JSON blob
  assessed_at  INTEGER NOT NULL
);

CREATE INDEX idx_churn_cluster ON churn_risk (cluster_tag, assessed_at);
```

---

## 1. Cadence Baseline & Drift Detection

Compare the last 7 days of posting activity to the prior 28-day baseline per cluster.

```typescript
interface ActivityRow {
  day: string;
  post_count: number;
  delete_count: number;
  session_count: number;
}

async function computeCadenceDrift(
  db: D1Database,
  cluster: string
): Promise<{ drift: number; deleteRatio: number }> {
  const today = new Date().toISOString().slice(0, 10);
  const { results } = await db
    .prepare(
      `SELECT day, post_count, delete_count, session_count
       FROM cluster_activity
       WHERE cluster_tag = ?
         AND day >= date(?, '-35 days')
         AND day < date(?, '-0 days')
       ORDER BY day ASC`
    )
    .bind(cluster, today, today)
    .all<ActivityRow>();

  const recent = results.slice(-7);
  const baseline = results.slice(0, 28);

  const avg = (rows: ActivityRow[]) =>
    rows.reduce((s, r) => s + r.post_count, 0) / Math.max(rows.length, 1);

  const recentAvg = avg(recent);
  const baselineAvg = avg(baseline);
  const drift = baselineAvg === 0 ? 0 : (baselineAvg - recentAvg) / baselineAvg;

  const totalPosts = recent.reduce((s, r) => s + r.post_count, 0);
  const totalDeletes = recent.reduce((s, r) => s + r.delete_count, 0);
  const deleteRatio = totalPosts === 0 ? 0 : totalDeletes / totalPosts;

  return { drift, deleteRatio };
}
```

---

## 2. Farewell Sentiment Classification with Workers AI

Sample recent posts from at-risk clusters and classify them for departure language.

```typescript
const FAREWELL_LABELS = ["farewell", "staying"] as const;

async function classifyFarewellSentiment(
  ai: Ai,
  postTexts: string[]
): Promise<number> {
  if (postTexts.length === 0) return 0;

  let farewellCount = 0;
  // Batch in groups of 10 to stay within Workers AI input limits
  for (let i = 0; i < postTexts.length; i += 10) {
    const batch = postTexts.slice(i, i + 10);
    const result = await ai.run("@cf/facebook/bart-large-mnli", {
      text: batch.join(" | "),
      candidate_labels: [...FAREWELL_LABELS],
    });
    // BART-MNLI returns labels sorted by score descending
    if (result.labels[0] === "farewell" && result.scores[0] > 0.6) {
      farewellCount++;
    }
  }

  return farewellCount / Math.ceil(postTexts.length / 10);
}
```

---

## 3. Cross-Cluster Link Share Decline

If a cluster stops referencing other clusters, it is becoming isolated — a precursor to exit.

```typescript
async function crossClusterLinkRatio(
  db: D1Database,
  cluster: string,
  windowDays = 7
): Promise<{ recent: number; baseline: number }> {
  const today = new Date().toISOString().slice(0, 10);
  const recentSince = `date('${today}', '-${windowDays} days')`;
  const baselineSince = `date('${today}', '-${windowDays + 28} days')`;

  const rows = await db
    .prepare(
      `SELECT
         SUM(CASE WHEN day >= ${recentSince} THEN cross_cluster_links ELSE 0 END) AS recent_links,
         SUM(CASE WHEN day < ${recentSince} AND day >= ${baselineSince} THEN cross_cluster_links ELSE 0 END) AS baseline_links
       FROM cluster_link_stats
       WHERE cluster_tag = ?`
    )
    .bind(cluster)
    .first<{ recent_links: number; baseline_links: number }>();

  return {
    recent: (rows?.recent_links ?? 0) / windowDays,
    baseline: (rows?.baseline_links ?? 0) / 28,
  };
}
```

---

## 4. Composite Risk Score & Storage

Combine the three signals into a weighted risk score and write to `churn_risk`.

```typescript
async function assessClusterChurnRisk(
  db: D1Database,
  ai: Ai,
  cluster: string,
  recentPosts: string[]
): Promise<number> {
  const [cadence, farewellRate, linkData] = await Promise.all([
    computeCadenceDrift(db, cluster),
    classifyFarewellSentiment(ai, recentPosts),
    crossClusterLinkRatio(db, cluster),
  ]);

  const linkDecline =
    linkData.baseline === 0
      ? 0
      : Math.max(0, (linkData.baseline - linkData.recent) / linkData.baseline);

  // Weighted sum — weights tuned empirically
  const riskScore = Math.min(
    1,
    cadence.drift * 0.4 +
    cadence.deleteRatio * 0.2 +
    farewellRate * 0.25 +
    linkDecline * 0.15
  );

  const signals = JSON.stringify({ cadenceDrift: cadence.drift, farewellRate, linkDecline });
  await db
    .prepare(
      `INSERT INTO churn_risk (id, cluster_tag, risk_score, signals, assessed_at)
       VALUES (?, ?, ?, ?, ?)`
    )
    .bind(crypto.randomUUID(), cluster, riskScore, signals, Date.now())
    .run();

  return riskScore;
}
```

---

## 5. Scheduled Sweep Worker

```typescript
// wrangler.toml: [triggers] crons = ["0 6 * * *"]
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const { results: clusters } = await env.DB
      .prepare(`SELECT DISTINCT cluster_tag FROM cluster_activity WHERE day >= date('now', '-7 days')`)
      .all<{ cluster_tag: string }>();

    for (const { cluster_tag } of clusters) {
      // Fetch a sample of recent post text (stored separately, redacted of PII)
      const { results: posts } = await env.DB
        .prepare(`SELECT content_snippet FROM posts WHERE cluster_tag = ? AND created_at > ? LIMIT 50`)
        .bind(cluster_tag, Date.now() - 7 * 86_400_000)
        .all<{ content_snippet: string }>();

      const texts = posts.map((p) => p.content_snippet);
      const risk = await assessClusterChurnRisk(env.DB, env.AI, cluster_tag, texts);

      if (risk >= 0.65) {
        await fetch(env.ALERT_WEBHOOK, {
          method: "POST",
          body: JSON.stringify({ event: "churn_risk_high", cluster: cluster_tag, score: risk }),
          headers: { "Content-Type": "application/json" },
        });
      }
    }
  },
};
```

---

## Anti-patterns

- **Treating a single day spike as churn signal** — short-term dips are normal (holidays,
  events). Always compare against a 28-day baseline, not yesterday.
- **Modelling at the session level** — anonymous sessions are too ephemeral; cluster-level
  aggregation is the right unit.
- **Storing full post text in `churn_risk`** — store only the `signals` JSON; full text
  raises retention and privacy concerns.
- **Alert fatigue** — only alert on clusters with at least 500 posts/week baseline to filter
  out tiny clusters with naturally noisy cadences.

---

## Gotchas

- `@cf/facebook/bart-large-mnli` has a payload size limit. Joining more than ~50 post
  snippets into a single text can exceed it — always batch.
- D1 `date()` functions use SQLite semantics: `date('now', '-7 days')` returns a TEXT string
  in YYYY-MM-DD format. Do not mix with JavaScript `Date.now()` integers in the same query.
- Clusters that lose members to *another cluster on the same platform* (migration vs. exodus)
  will show similar signals — disambiguate by checking whether the destination cluster shows
  a corresponding rise in new session volume.

---

## Verification

```bash
# Simulate 30 days of normal activity then 7-day drop
wrangler d1 execute example project_DB --command "
  INSERT INTO cluster_activity SELECT 'test-cluster', date('now', '-' || n || ' days'), 100, 2, 80, 0, 0
  FROM (WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<35) SELECT n FROM r);
  UPDATE cluster_activity SET post_count = 20, delete_count = 15
  WHERE cluster_tag='test-cluster' AND day >= date('now','-7 days');
"
# Run locally
wrangler dev --test-scheduled
# Confirm churn_risk row with score >= 0.65
wrangler d1 execute example project_DB --command "SELECT * FROM churn_risk WHERE cluster_tag='test-cluster'"
```

---

## Related

- `platform-health-score-dashboard-analytics-engine.md`
- `anonymous-community-health-scoring-d1.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `shadow-banning-reach-limiting-d1-workers.md`

---

## Sources

- Cloudflare Workers AI — https://developers.cloudflare.com/workers-ai/
- Cloudflare D1 — https://developers.cloudflare.com/d1/
- "Predicting Community Exodus in Online Social Networks" — WWW 2023
- example project internal community health spec v1.4
