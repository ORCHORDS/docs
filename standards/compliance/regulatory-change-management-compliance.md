# Regulatory Change Management for Compliance Teams

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your compliance team learns about a new regulation (e.g., the EU AI Act's August 2026 general application date, PCI DSS v4.0 future-dated requirements taking effect March 2025, or a new US state privacy law effective January 2027) through a news alert rather than a systematic horizon-scanning process. The gap between awareness and implementation readiness creates legal exposure. ISO 27001:2022 Annex A control A.5.31 (Legal, statutory, regulatory and contractual requirements) and SOC 2 CC9.2 require a documented process for identifying and responding to regulatory changes that affect information security and privacy.

---

## Context

The global regulatory landscape for cloud-native and data-driven products has accelerated significantly since 2022. In 2025–2026 alone, the following frameworks entered force or reached major application milestones:

- EU AI Act (August 2024 entry into force, phased application through 2027)
- PCI DSS v4.0 future-dated requirements (March 2025)
- NIS2 Directive (October 2024 transposition deadline)
- EU Cyber Resilience Act (December 2027 application, with vulnerability disclosure from 2026)
- DORA (January 2025 application)
- India DPDP Rules (notified 2025)
- US state privacy laws (12+ new states in 2025–2026)
- UK Online Safety Act (multiple commencement orders, 2025–2026)

Without a structured regulatory change management process, organisations suffer from:

1. **Late awareness** — legal counsel notifies engineering weeks before an application deadline.
2. **No gap assessment** — it is unknown which existing controls satisfy the new requirement and which do not.
3. **Undocumented decisions** — informal Slack discussions substitute for a formal risk acceptance or remediation record.
4. **Audit exposure** — auditors find no evidence that the organisation monitored and responded to regulatory changes.

This article describes an end-to-end regulatory change management workflow, including horizon scanning, gap assessment, a remediation register, and a Cloudflare Workers–based status page for cross-functional visibility.

---

## Horizon Scanning Architecture

### 5.1 Source Taxonomy

Classify sources by reliability tier:

| Tier | Sources | Cadence |
|---|---|---|
| 1 — Primary | Official gazette (EUR-Lex, Federal Register, UK Legislation), supervisory authority publications (EDPB, ICO, FTC) | Daily |
| 2 — Secondary | Law firm client alerts (Fieldfisher, Freshfields, DLA Piper), IAPP Westin Research, ENISA | Weekly |
| 3 — Tertiary | Industry press (iapp.org, legaltech news), conference CFPs | Monthly |

### 5.2 Automated Ingestion with a Workers Cron Job

```typescript
// src/regulatory-scanner.ts
// Scheduled Worker — runs daily at 06:00 UTC
// Fetches RSS/Atom feeds from tier-1 sources and stores new items

interface FeedItem {
  id:          string;
  title:       string;
  link:        string;
  summary:     string;
  publishedAt: string;
  source:      string;
}

const TIER1_FEEDS = [
  { name: 'EUR-Lex New Acts', url: 'https://eur-lex.europa.eu/tools/rss.do?lang=en&type=act' },
  { name: 'Federal Register', url: 'https://www.federalregister.gov/articles/search.rss?publication_type[]=RULE' },
  { name: 'ICO News',         url: 'https://ico.org.uk/about-the-ico/news-and-events/rss.xml' },
  { name: 'EDPB Press',       url: 'https://www.edpb.europa.eu/edpb/rss-rss_en.xml' },
];

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    for (const feed of TIER1_FEEDS) {
      try {
        const resp = await fetch(feed.url, {
          headers: { 'User-Agent': 'ComplianceBot/1.0 (+https://example.com/compliance)' }
        });
        if (!resp.ok) continue;

        const xml = await resp.text();
        const items = parseRssFeed(xml, feed.name);

        for (const item of items) {
          // Dedup by item ID (GUID or link)
          const existing = await env.DB.prepare(
            'SELECT id FROM reg_feed_items WHERE item_id = ?'
          ).bind(item.id).first();
          if (existing) continue;

          await env.DB.prepare(`
            INSERT INTO reg_feed_items
              (item_id, title, link, summary, source, published_at, ingested_at, reviewed)
            VALUES (?, ?, ?, ?, ?, ?, unixepoch(), 0)
          `).bind(item.id, item.title, item.link, item.summary.slice(0, 1000), item.source, item.publishedAt).run();
        }
      } catch (err) {
        console.error(`Feed error ${feed.name}:`, err);
      }
    }

    // Alert if unreviewed items > 20 (backlog signal)
    const count = await env.DB.prepare(
      'SELECT COUNT(*) AS n FROM reg_feed_items WHERE reviewed = 0'
    ).first<{ n: number }>();
    if ((count?.n ?? 0) > 20) {
      await notifySlack(env, `Regulatory scan backlog: ${count?.n} unreviewed items`);
    }
  }
};

function parseRssFeed(xml: string, source: string): FeedItem[] {
  const items: FeedItem[] = [];
  const blocks = xml.matchAll(/<item>([\s\S]*?)<\/item>/g);
  for (const block of blocks) {
    const inner = block[1];
    items.push({
      id:          inner.match(/<guid[^>]*>([^<]+)<\/guid>/)?.[1] ?? '',
      title:       stripCdata(inner.match(/<title[^>]*>([\s\S]*?)<\/title>/)?.[1] ?? ''),
      link:        inner.match(/<link[^>]*>([^<]+)<\/link>/)?.[1] ?? '',
      summary:     stripCdata(inner.match(/<description[^>]*>([\s\S]*?)<\/description>/)?.[1] ?? ''),
      publishedAt: inner.match(/<pubDate>([^<]+)<\/pubDate>/)?.[1] ?? '',
      source,
    });
  }
  return items;
}

function stripCdata(s: string): string {
  return s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1').trim();
}

async function notifySlack(env: Env, text: string) {
  await fetch(env.SLACK_WEBHOOK_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ text }),
  });
}
```

---

## Regulatory Change Register (D1 Schema)

```sql
-- migrations/0001_regulatory_change.sql

-- Raw feed items from scanning
CREATE TABLE IF NOT EXISTS reg_feed_items (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  item_id      TEXT    UNIQUE NOT NULL,
  title        TEXT    NOT NULL,
  link         TEXT    NOT NULL,
  summary      TEXT,
  source       TEXT    NOT NULL,
  published_at TEXT,
  ingested_at  INTEGER NOT NULL,
  reviewed     INTEGER NOT NULL DEFAULT 0,
  change_id    INTEGER  -- FK to reg_changes once triaged
);

-- Triage-confirmed regulatory changes
CREATE TABLE IF NOT EXISTS reg_changes (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  title            TEXT    NOT NULL,
  regulation       TEXT    NOT NULL,   -- e.g. 'EU AI Act', 'PCI DSS v4.0'
  jurisdiction     TEXT    NOT NULL,   -- e.g. 'EU', 'US-CA', 'Global'
  effective_date   TEXT    NOT NULL,   -- ISO 8601
  description      TEXT    NOT NULL,
  impact_rating    TEXT    NOT NULL CHECK(impact_rating IN ('critical','high','medium','low','informational')),
  owner_email      TEXT    NOT NULL,   -- DRI (directly responsible individual)
  status           TEXT    NOT NULL DEFAULT 'identified'
                            CHECK(status IN ('identified','assessed','in-remediation','closed','risk-accepted')),
  gap_summary      TEXT,
  remediation_due  TEXT,              -- ISO 8601
  created_at       INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at       INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Remediation tasks linked to a change
CREATE TABLE IF NOT EXISTS reg_tasks (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  change_id   INTEGER NOT NULL REFERENCES reg_changes(id),
  title       TEXT    NOT NULL,
  assignee    TEXT    NOT NULL,
  due_date    TEXT,
  status      TEXT    NOT NULL DEFAULT 'open' CHECK(status IN ('open','in-progress','done','blocked')),
  notes       TEXT,
  updated_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_changes_status  ON reg_changes(status);
CREATE INDEX IF NOT EXISTS idx_changes_eff     ON reg_changes(effective_date);
CREATE INDEX IF NOT EXISTS idx_tasks_change    ON reg_tasks(change_id);
```

---

## Regulatory Change Dashboard (Workers API)

```typescript
// src/reg-change-api.ts
// GET /api/changes?status=in-remediation&jurisdiction=EU

export async function handleChangesApi(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const status       = url.searchParams.get('status');
  const jurisdiction = url.searchParams.get('jurisdiction');
  const dueBefore    = url.searchParams.get('due_before'); // ISO date

  let query = 'SELECT * FROM reg_changes WHERE 1=1';
  const bindings: unknown[] = [];

  if (status) {
    query += ' AND status = ?';
    bindings.push(status);
  }
  if (jurisdiction) {
    query += ' AND (jurisdiction = ? OR jurisdiction = "Global")';
    bindings.push(jurisdiction);
  }
  if (dueBefore) {
    query += ' AND remediation_due <= ?';
    bindings.push(dueBefore);
  }

  query += ' ORDER BY effective_date ASC LIMIT 100';

  const stmt = env.DB.prepare(query);
  const result = await (bindings.length > 0
    ? stmt.bind(...bindings)
    : stmt
  ).all();

  return Response.json({
    changes: result.results,
    meta: { count: result.results.length, generatedAt: new Date().toISOString() }
  });
}

// POST /api/changes — create a new regulatory change record
export async function createChange(request: Request, env: Env): Promise<Response> {
  const body = await request.json() as {
    title: string;
    regulation: string;
    jurisdiction: string;
    effective_date: string;
    description: string;
    impact_rating: string;
    owner_email: string;
    remediation_due?: string;
  };

  const result = await env.DB.prepare(`
    INSERT INTO reg_changes
      (title, regulation, jurisdiction, effective_date, description,
       impact_rating, owner_email, status, remediation_due)
    VALUES (?, ?, ?, ?, ?, ?, ?, 'identified', ?)
  `).bind(
    body.title, body.regulation, body.jurisdiction, body.effective_date,
    body.description, body.impact_rating, body.owner_email,
    body.remediation_due ?? null
  ).run();

  return Response.json({ id: result.meta.last_row_id }, { status: 201 });
}
```

---

## Escalation and Overdue Alerting

```typescript
// src/reg-escalation.ts — Cron trigger: daily at 08:00 UTC
export default {
  async scheduled(_: ScheduledEvent, env: Env) {
    const today = new Date().toISOString().slice(0, 10);

    // Changes whose effective date is within 30 days and not yet closed
    const upcoming = await env.DB.prepare(`
      SELECT id, title, regulation, effective_date, owner_email, status
      FROM reg_changes
      WHERE effective_date BETWEEN ? AND DATE(?, '+30 days')
        AND status NOT IN ('closed', 'risk-accepted')
      ORDER BY effective_date ASC
    `).bind(today, today).all();

    // Changes with overdue remediation tasks
    const overdue = await env.DB.prepare(`
      SELECT rc.id, rc.title, rc.regulation, rt.title AS task_title,
             rt.assignee, rt.due_date
      FROM reg_tasks rt
      JOIN reg_changes rc ON rc.id = rt.change_id
      WHERE rt.due_date < ?
        AND rt.status NOT IN ('done')
    `).bind(today).all();

    if (upcoming.results.length > 0 || overdue.results.length > 0) {
      const text = [
        upcoming.results.length > 0
          ? `*Regulatory changes due within 30 days:* ${upcoming.results.map((c: any) => `${c.title} (${c.effective_date})`).join(', ')}`
          : null,
        overdue.results.length > 0
          ? `*Overdue remediation tasks:* ${overdue.results.map((t: any) => `${t.task_title} (${t.assignee})`).join(', ')}`
          : null,
      ].filter(Boolean).join('\n');

      await fetch(env.COMPLIANCE_SLACK_WEBHOOK, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ text }),
      });
    }
  }
};
```

---

## Anti-patterns

- **Relying on a single lawyer for horizon scanning.** Legal counsel provides interpretation, not systematic surveillance. Automate tier-1 feed ingestion and assign the compliance team (not legal) to triage.
- **Creating change records only when a fine is looming.** Regulatory change management requires proactive gap assessment, often 12–24 months before an effective date, to allow for engineering sprints, vendor contract renegotiation, and board approval of material changes.
- **Using Jira tickets as the regulatory register.** Jira lacks effective date tracking, jurisdiction tagging, and impact rating fields that auditors expect. A purpose-built register (even a simple D1 schema) with a read-only audit trail is more defensible.
- **Marking a change as "closed" without evidence.** Auditors expect evidence artefacts (updated policy documents, test results, architecture decision records) linked to each closed change.
- **Treating "informational" items as noise.** Low-rated changes sometimes precede enforcement guidance that reclassifies them as critical. Retain all items in the register and review quarterly.

---

## Gotchas

- **Effective date ≠ enforcement date.** Regulations often have a 6–12 month gap between the effective date (when obligations technically apply) and active regulatory enforcement. Do not use this gap as implementation slack — supervisory authorities may take enforcement action from day one.
- **Third-party processors must also comply.** When a new regulation imposes obligations on data processors, your DPAs with Cloudflare, your analytics vendor, and your CRM provider may need amendment before your own effective date.
- **Jurisdictional overlap.** A single product may be subject to GDPR, CCPA/CPRA, LGPD, and APPI simultaneously. A regulation affecting one jurisdiction's data subjects may trigger obligations under another (e.g., GDPR Chapter V transfers triggered by a US state law's new data sharing mandate).
- **Currency of the register matters for ISO 27001 audits.** Auditors will check the `updated_at` timestamps. A register that has not been updated in six months is treated as unevidenced, regardless of actual compliance posture.

---

## Verification

```bash
# 1. Check feed ingestion ran today
npx wrangler d1 execute compliance-db \
  --command "SELECT source, COUNT(*) AS n, MAX(ingested_at) AS last FROM reg_feed_items GROUP BY source;"

# 2. List open critical changes
npx wrangler d1 execute compliance-db \
  --command "SELECT title, regulation, effective_date, owner_email FROM reg_changes WHERE impact_rating='critical' AND status NOT IN ('closed','risk-accepted') ORDER BY effective_date;"

# 3. Confirm overdue alert fires in staging
npx wrangler dev --test-scheduled

# 4. Pull a JSON export for the board report
curl 'https://compliance.example.workers.dev/api/changes?status=in-remediation' \
  -H 'Authorization: Bearer YOUR_TOKEN' | jq '.changes[] | {title, regulation, effective_date}'
```

---

## Related

- `iso-27001-management-review.md` — management review inputs including regulatory change status
- `security-policy-lifecycle-management.md` — policy update triggers from regulatory changes
- `audit-log-mandatory.md` — evidence retention for change management records

---

## Sources

- ISO/IEC 27001:2022 Annex A A.5.31 — Legal, statutory, regulatory and contractual requirements
- SOC 2 TSC CC9.2 — vendor and business partner risk management (addresses external regulatory change)
- IAPP Privacy Resource Centre — https://iapp.org/resources/
- EUR-Lex RSS feeds — https://eur-lex.europa.eu/tools/rss.do
- ENISA regulatory outlook publications — https://www.enisa.europa.eu/publications
- UK Legislation.gov.uk — https://www.legislation.gov.uk/new
