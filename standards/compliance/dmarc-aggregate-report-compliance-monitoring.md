# DMARC Aggregate Report Compliance Monitoring

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Your domain sends email through Cloudflare Email Routing, transactional providers (SendGrid, Postmark, AWS SES), and marketing platforms. DMARC policy is published at `p=quarantine` or `p=reject`, but you have no systematic process to consume the XML aggregate reports (`rua` recipients), detect misaligned senders, or produce evidence for audits (SOC 2, ISO 27001, HIPAA Addressable § 164.312(e)(2)) that email authentication is continuously enforced. Unauthenticated phishing pretending to be your domain triggers regulatory breach notifications in several jurisdictions once it causes harm.

---

## Context

DMARC (RFC 7489) lets receiving mail servers send aggregate feedback reports (RUA) and forensic failure reports (RUF) to addresses you specify in your DNS TXT record. RUA reports are gzip-compressed XML delivered as email attachments, typically once per day per reporting organisation. At scale — after a domain reaches broad sending volume — dozens of ISPs (Gmail, Yahoo, Outlook, Comcast, Apple) each submit daily reports. Without automation:

- SPF `include` chains break silently when a third-party ESP changes its IP ranges.
- DKIM selectors expire after a key rotation that was not propagated to all signing services.
- Shadow IT email (a SaaS tool a team set up without IT awareness) shows up as `fail` rows that are invisible until someone manually opens XML.
- Regulators (FCA, BaFin, NIS2 Article 21 §2(h)) increasingly treat demonstrated email domain spoofing protection as a baseline security control.

DMARC aggregate report monitoring is therefore both a deliverability hygiene practice and an evidence-generation requirement for multiple compliance frameworks.

**Glossary**

| Term | Meaning |
|---|---|
| RUA | Reporting URI for Aggregate — `mailto:` or `https:` endpoint that receives XML reports |
| RUF | Reporting URI for Forensic — individual message samples (rare, privacy-sensitive) |
| `p=` | Domain policy: `none`, `quarantine`, `reject` |
| `sp=` | Subdomain policy override |
| `pct=` | Percentage of messages the policy applies to (default 100) |
| SPF alignment | `mailfrom` domain matches `From:` header domain |
| DKIM alignment | `d=` tag in DKIM-Signature matches `From:` domain |

---

## DNS Record and RUA Endpoint Design

### 1.1 Publish a DMARC Record with a Workers RUA Endpoint

Deliver reports to a Workers endpoint rather than a bare mailbox so you can parse, store, and alert in real time.

```txt
; DNS TXT record for _dmarc.example.com
v=DMARC1; p=reject; sp=reject; pct=100;
  rua=mailto:dmarc-rua@example.com,https://dmarc-ingest.example.workers.dev/rua;
  ruf=mailto:dmarc-ruf@example.com;
  adkim=s; aspf=s; fo=1; rf=afrf; ri=86400
```

Key policy flags:
- `adkim=s` — strict DKIM alignment: signing domain must exactly match `From:` domain, not just be a subdomain.
- `aspf=s` — strict SPF alignment.
- `fo=1` — generate forensic reports for any auth failure (as opposed to `fo=0` which is only total failure).
- `ri=86400` — request daily aggregation interval.

### 1.2 Workers Ingest Endpoint

Receiving ISPs POST gzip+XML to your `https:` RUA endpoint. The Worker validates the source, decompresses, parses, and writes to D1.

```typescript
// src/dmarc-ingest.ts
import { gunzipSync } from 'node:zlib';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const ct = request.headers.get('content-type') ?? '';
    const buf = await request.arrayBuffer();
    let xmlText: string;

    if (ct.includes('gzip') || ct.includes('zip')) {
      try {
        xmlText = new TextDecoder().decode(gunzipSync(new Uint8Array(buf)));
      } catch {
        return new Response('Invalid compressed payload', { status: 400 });
      }
    } else {
      xmlText = new TextDecoder().decode(buf);
    }

    // Minimal XML parse — production code should use a full XML parser
    const orgName = xmlText.match(/<org_name>([^<]+)<\/org_name>/)?.[1] ?? 'unknown';
    const reportId = xmlText.match(/<report_id>([^<]+)<\/report_id>/)?.[1] ?? crypto.randomUUID();
    const begin = parseInt(xmlText.match(/<begin>(\d+)<\/begin>/)?.[1] ?? '0');
    const end = parseInt(xmlText.match(/<end>(\d+)<\/end>/)?.[1] ?? '0');

    // Extract all <record> blocks
    const records: RuaRecord[] = parseRecords(xmlText);

    const failedRecords = records.filter(r =>
      r.dkimResult !== 'pass' || r.spfResult !== 'pass'
    );

    await env.DB.prepare(
      `INSERT OR IGNORE INTO dmarc_reports
       (report_id, org_name, begin_ts, end_ts, total_count, fail_count, raw_xml, ingested_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      reportId, orgName, begin, end,
      records.length, failedRecords.length,
      xmlText.slice(0, 65536),
      Date.now()
    ).run();

    for (const rec of failedRecords) {
      await env.DB.prepare(
        `INSERT INTO dmarc_failures
         (report_id, source_ip, count, disposition, dkim_result, spf_result, header_from)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        reportId, rec.sourceIp, rec.count,
        rec.disposition, rec.dkimResult, rec.spfResult, rec.headerFrom
      ).run();
    }

    // Alert if fail rate > 1 %
    if (records.length > 0 && failedRecords.length / records.length > 0.01) {
      await env.ALERT_QUEUE.send({
        type: 'dmarc_fail_spike',
        reportId, orgName,
        failRate: failedRecords.length / records.length,
      });
    }

    return new Response('Accepted', { status: 202 });
  }
};

interface RuaRecord {
  sourceIp: string;
  count: number;
  disposition: string;
  dkimResult: string;
  spfResult: string;
  headerFrom: string;
}

function parseRecords(xml: string): RuaRecord[] {
  const records: RuaRecord[] = [];
  const recordBlocks = xml.matchAll(/<record>([\s\S]*?)<\/record>/g);
  for (const block of recordBlocks) {
    const inner = block[1];
    records.push({
      sourceIp:    inner.match(/<source_ip>([^<]+)<\/source_ip>/)?.[1] ?? '',
      count:       parseInt(inner.match(/<count>(\d+)<\/count>/)?.[1] ?? '1'),
      disposition: inner.match(/<disposition>([^<]+)<\/disposition>/)?.[1] ?? 'none',
      dkimResult:  inner.match(/<dkim>([^<]+)<\/dkim>/)?.[1] ?? 'fail',
      spfResult:   inner.match(/<spf>([^<]+)<\/spf>/)?.[1] ?? 'fail',
      headerFrom:  inner.match(/<header_from>([^<]+)<\/header_from>/)?.[1] ?? '',
    });
  }
  return records;
}
```

---

## D1 Schema and Retention

```sql
-- migrations/0001_dmarc.sql
CREATE TABLE IF NOT EXISTS dmarc_reports (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id    TEXT    UNIQUE NOT NULL,
  org_name     TEXT    NOT NULL,
  begin_ts     INTEGER NOT NULL,
  end_ts       INTEGER NOT NULL,
  total_count  INTEGER NOT NULL DEFAULT 0,
  fail_count   INTEGER NOT NULL DEFAULT 0,
  raw_xml      TEXT,
  ingested_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS dmarc_failures (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id    TEXT    NOT NULL REFERENCES dmarc_reports(report_id),
  source_ip    TEXT    NOT NULL,
  count        INTEGER NOT NULL DEFAULT 1,
  disposition  TEXT    NOT NULL,
  dkim_result  TEXT    NOT NULL,
  spf_result   TEXT    NOT NULL,
  header_from  TEXT    NOT NULL,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_failures_source ON dmarc_failures(source_ip);
CREATE INDEX IF NOT EXISTS idx_failures_report ON dmarc_failures(report_id);
CREATE INDEX IF NOT EXISTS idx_reports_ingested ON dmarc_reports(ingested_at);

-- Purge raw XML after 90 days for storage efficiency (keep aggregates)
-- Run as a scheduled Worker
-- UPDATE dmarc_reports SET raw_xml = NULL WHERE ingested_at < unixepoch() - 7776000;
```

For ISO 27001 and SOC 2 audit evidence, retain aggregate counts and failure rows for at least 12 months. The raw XML is optional beyond 90 days.

---

## Scheduled Compliance Digest

A Cron Trigger Worker generates a weekly compliance digest and posts it to a compliance Slack channel or email, giving the security team a standing audit trail.

```typescript
// src/dmarc-digest.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const since = Math.floor(Date.now() / 1000) - 7 * 86400; // last 7 days

    const summary = await env.DB.prepare(`
      SELECT
        COUNT(*)                                          AS report_count,
        SUM(total_count)                                 AS total_messages,
        SUM(fail_count)                                  AS failed_messages,
        ROUND(100.0 * SUM(fail_count) / NULLIF(SUM(total_count),0), 2) AS fail_pct,
        COUNT(DISTINCT org_name)                         AS reporting_orgs
      FROM dmarc_reports
      WHERE begin_ts >= ?
    `).bind(since).first<{
      report_count: number;
      total_messages: number;
      failed_messages: number;
      fail_pct: number;
      reporting_orgs: number;
    }>();

    const topFailingSources = await env.DB.prepare(`
      SELECT source_ip, SUM(count) AS cnt
      FROM dmarc_failures
      WHERE created_at >= ?
      GROUP BY source_ip
      ORDER BY cnt DESC
      LIMIT 10
    `).bind(since).all();

    const body = JSON.stringify({
      text: `*DMARC Weekly Digest* (${new Date().toISOString().slice(0,10)})\n` +
            `Reports received: ${summary?.report_count}\n` +
            `Messages evaluated: ${summary?.total_messages?.toLocaleString()}\n` +
            `Auth failures: ${summary?.failed_messages?.toLocaleString()} (${summary?.fail_pct}%)\n` +
            `Reporting organisations: ${summary?.reporting_orgs}\n` +
            `Top failing IPs: ${topFailingSources.results.map((r: any) => `${r.source_ip} (${r.cnt})`).join(', ')}`
    });

    await fetch(env.SLACK_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body,
    });
  }
};
```

```toml
# wrangler.toml excerpt
[[triggers]]
  crons = ["0 9 * * MON"]  # Every Monday 09:00 UTC
```

---

## Anti-patterns

- **Publishing `p=none` indefinitely.** The monitoring-only policy is a transition phase, not a destination. Set a calendar reminder to move to `p=quarantine` after 30 days of clean reports.
- **Using only a mailbox for RUA.** A shared mailbox fills up, is not parsed, and provides no audit trail. Always pair with a structured ingest endpoint.
- **Not monitoring subdomains.** Attackers spoof `marketing.example.com` or `noreply.example.com` if `sp=` is unset. Explicitly set `sp=reject` unless a subdomain policy exception is documented.
- **Treating `spf=pass` as sufficient.** SPF alone does not prove DMARC alignment. The `mailfrom` domain must align with `From:` header. An ESP authenticated via SPF on `esp.example.net` will still DMARC-fail if your policy requires strict alignment.
- **Rotating DKIM keys without updating all signing services.** Key rotation is a common source of sudden fail spikes. Rotate keys in a two-step process: publish the new key (selector2), update the signing service, then remove the old key after one full report cycle confirms the new selector is appearing.

---

## Gotchas

- **`ri=86400` is advisory.** Major ISPs (Google, Microsoft) may send reports every few hours during high-volume periods, regardless of your `ri` value.
- **RUF reports contain full message headers and may contain personal data.** Forensic report collection is disabled by default at many ISPs (Yahoo, Apple have stopped sending them). Treat any RUF data as personal data under GDPR/CCPA and restrict access accordingly.
- **Third-party aggregate services (Postmark, MxToolBox, BIMI Group, Valimail).** These are convenient but add a third-party data processor to your email metadata. A DMARC DPA addendum is required under GDPR Article 28.
- **BIMI requires `p=quarantine` or `p=reject` plus a Valid Mark Certificate (VMC) from a CA.** BIMI implementation is out of scope here but is predicated on a mature DMARC posture.
- **D1 is eventually consistent on reads.** For the compliance digest, query via the primary instance binding, not the read-replica, to avoid reporting stale data.

---

## Verification

```bash
# 1. Confirm DNS record is published
dig TXT _dmarc.example.com +short

# 2. Trigger a test report from Google Postmaster Tools
# (manual step — log in to postmaster.google.com)

# 3. Verify ingest endpoint is reachable
curl -X POST https://dmarc-ingest.example.workers.dev/rua \
  -H 'content-type: text/xml' \
  -d @test-report.xml

# 4. Query D1 for latest ingested reports
npx wrangler d1 execute dmarc-db \
  --command "SELECT report_id, org_name, total_count, fail_count FROM dmarc_reports ORDER BY ingested_at DESC LIMIT 5;"

# 5. Confirm fail-rate alert fires correctly in staging
npx wrangler dev --test-scheduled
```

Compliance acceptance criterion: fail_pct < 0.1 % on a rolling 7-day window with `p=reject`.

---

## Related

- `nis2-article-21-technical-measures-workers.md` — NIS2 baseline security controls including email authentication
- `soc2-cc6-logical-access-controls.md` — access controls that pair with domain authentication evidence
- `audit-log-mandatory.md` — log retention requirements applicable to DMARC data

---

## Sources

- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- RFC 6376 — DomainKeys Identified Mail (DKIM)
- RFC 7208 — Sender Policy Framework (SPF)
- Google Postmaster Tools — https://postmaster.google.com
- M3AAWG DMARC Deployment Best Practices (2024)
- NIS2 Directive Article 21(2)(h) — authentication controls
- Cloudflare Email Routing documentation — https://developers.cloudflare.com/email-routing/
