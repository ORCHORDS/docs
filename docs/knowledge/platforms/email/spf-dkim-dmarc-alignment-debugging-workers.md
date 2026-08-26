# SPF/DKIM/DMARC Alignment Debugging and Monitoring with Workers

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Outbound email passes SPF and DKIM individually but still fails DMARC, causing messages to be rejected or quarantined at major receivers. The problem is not authentication itself but alignment — the RFC 5322 `From:` domain does not match the domain authenticated by SPF (envelope-from / Return-Path) or DKIM (the `d=` tag in the DKIM-Signature header). A Cloudflare Worker that parses inbound DMARC aggregate reports and emits structured alignment failure events makes these mismatches discoverable before they affect deliverability at scale.

## Context

DMARC alignment requires that at least one of SPF or DKIM passes AND that the authenticated domain aligns with the `From:` header domain. Strict alignment requires an exact match; relaxed alignment (the default) allows organisational-domain matching (e.g. `From: user@mail.example.com` aligns with SPF result for `example.com`). ESP sub-domain sending, forwarding chains, and mailing list rewrites are the most common sources of alignment failures. Because receivers send aggregate reports (RUA) as gzipped XML attached to email, a Worker-based ingestion pipeline is necessary to decode, normalise, and store alignment metrics in a queryable form for trend analysis.

## DMARC Alignment Mechanics

### Identifier Alignment Rules (RFC 7489 §3.1)

| Check    | Identifier used       | Strict match                          | Relaxed match                       |
|----------|-----------------------|---------------------------------------|-------------------------------------|
| SPF      | envelope-from (MAIL FROM) | MAIL FROM domain == From: domain | Org domain of MAIL FROM == org domain of From: |
| DKIM     | `d=` tag in DKIM-Signature | `d=` value == From: domain      | Org domain of `d=` == org domain of From: |

### Common Alignment Failure Scenarios

1. **ESP envelope rewrite**: ESP sends with `MAIL FROM: bounce@esp-provider.com`; your `From:` is `@yourco.com`. SPF passes for esp-provider.com but does not align with yourco.com. Fix: configure a custom bounce domain (`bounce.yourco.com`) and add it to your SPF record.
2. **Shared DKIM signing**: ESP signs with `d=esp-provider.com`. Fix: configure per-domain or sub-domain DKIM signing.
3. **Mailing list rewrite**: List manager rewrites From or envelope-from. ARC (Authenticated Received Chain) is the long-term fix; DMARC `p=none` on the list-receiving domain is a short-term workaround.
4. **Forwarding**: Destination server checks SPF against the forwarding server's IP. Fix: SRS (Sender Rewriting Scheme) or rely on DKIM if the body is unchanged.

## Worker — DMARC RUA Report Ingestion

Workers can receive DMARC reports via Email Routing when the `rua=mailto:dmarc-reports@yourco.com` address is routed to a Worker.

```typescript
// src/dmarc-ingest.ts
import { EmailMessage } from 'cloudflare:email';
import { gunzipSync } from 'node:zlib';

export interface Env {
  DB: D1Database;
  DMARC_ALERT_QUEUE: Queue;
}

export default {
  async email(message: EmailMessage, env: Env): Promise<void> {
    // DMARC aggregate reports arrive as MIME attachments (.xml.gz or .zip)
    const raw = await streamToBuffer(message.raw);
    const attachments = extractAttachments(raw);

    for (const att of attachments) {
      const xml = att.isGzip ? gunzipSync(att.data).toString('utf-8') : att.data.toString('utf-8');
      const report = parseDmarcXml(xml);
      await storeReport(env.DB, report);
      const failures = report.records.filter(r => r.dmarc_result === 'fail');
      if (failures.length > 0) {
        await env.DMARC_ALERT_QUEUE.send({ report_id: report.report_id, failures });
      }
    }
  },
};

interface DmarcRecord {
  source_ip:       string;
  count:           number;
  envelope_from:   string;
  header_from:     string;
  spf_domain:      string;
  spf_result:      string;
  spf_aligned:     boolean;
  dkim_domain:     string;
  dkim_result:     string;
  dkim_aligned:    boolean;
  dmarc_result:    string;  // 'pass' | 'fail'
}

interface DmarcReport {
  report_id:    string;
  org_name:     string;
  begin_epoch:  number;
  end_epoch:    number;
  policy_domain: string;
  policy_p:     string;
  policy_pct:   number;
  records:      DmarcRecord[];
}

function parseDmarcXml(xml: string): DmarcReport {
  // Minimal XPath-free parser targeting the RFC 7489 Appendix C schema.
  // In production use a proper XML parser (e.g. fast-xml-parser bundled in the Worker).
  const get = (tag: string) => {
    const m = xml.match(new RegExp(`<${tag}[^>]*>([^<]*)<\/${tag}>`));
    return m ? m[1].trim() : '';
  };
  const getAll = (tag: string) => {
    const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\/${tag}>`, 'g');
    const out: string[] = [];
    let m: RegExpExecArray | null;
    while ((m = re.exec(xml)) !== null) out.push(m[1]);
    return out;
  };

  const recordBlocks = getAll('record');
  const records: DmarcRecord[] = recordBlocks.map(block => {
    const bg = (t: string) => block.match(new RegExp(`<${t}[^>]*>([^<]*)<\/${t}>`))?.[1].trim() ?? '';
    const spfResult  = bg('spf').match(/<result>([^<]*)<\/result>/)?.[1] ?? '';
    const dkimResult = bg('dkim').match(/<result>([^<]*)<\/result>/)?.[1] ?? '';
    const spfDomain  = bg('spf').match(/<domain>([^<]*)<\/domain>/)?.[1] ?? '';
    const dkimDomain = bg('dkim').match(/<domain>([^<]*)<\/domain>/)?.[1] ?? '';
    const headerFrom = bg('header_from');
    const orgDomain  = (d: string) => d.split('.').slice(-2).join('.');

    return {
      source_ip:     bg('source_ip'),
      count:         Number(bg('count')),
      envelope_from: bg('envelope_from'),
      header_from:   headerFrom,
      spf_domain:    spfDomain,
      spf_result:    spfResult,
      spf_aligned:   orgDomain(spfDomain) === orgDomain(headerFrom),
      dkim_domain:   dkimDomain,
      dkim_result:   dkimResult,
      dkim_aligned:  orgDomain(dkimDomain) === orgDomain(headerFrom),
      dmarc_result:  bg('disposition') === 'none' && (spfResult === 'pass' || dkimResult === 'pass')
                       ? 'pass' : 'fail',
    };
  });

  return {
    report_id:     get('report_id'),
    org_name:      get('org_name'),
    begin_epoch:   Number(get('begin')),
    end_epoch:     Number(get('end')),
    policy_domain: get('domain'),
    policy_p:      get('p'),
    policy_pct:    Number(get('pct') || '100'),
    records,
  };
}
```

## D1 Schema for Alignment Metrics

```sql
-- migrations/0001_dmarc_reports.sql

CREATE TABLE IF NOT EXISTS dmarc_reports (
  id             TEXT PRIMARY KEY,
  org_name       TEXT NOT NULL,
  policy_domain  TEXT NOT NULL,
  policy_p       TEXT NOT NULL,
  policy_pct     INTEGER NOT NULL DEFAULT 100,
  begin_epoch    INTEGER NOT NULL,
  end_epoch      INTEGER NOT NULL,
  ingested_at    INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS dmarc_records (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id      TEXT NOT NULL REFERENCES dmarc_reports(id) ON DELETE CASCADE,
  source_ip      TEXT NOT NULL,
  message_count  INTEGER NOT NULL DEFAULT 1,
  envelope_from  TEXT,
  header_from    TEXT NOT NULL,
  spf_domain     TEXT,
  spf_result     TEXT,
  spf_aligned    INTEGER NOT NULL DEFAULT 0,
  dkim_domain    TEXT,
  dkim_result    TEXT,
  dkim_aligned   INTEGER NOT NULL DEFAULT 0,
  dmarc_result   TEXT NOT NULL,           -- 'pass' | 'fail'
  created_at     INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_dmarc_domain  ON dmarc_records (header_from, dmarc_result);
CREATE INDEX idx_dmarc_src_ip  ON dmarc_records (source_ip);
CREATE INDEX idx_dmarc_epoch   ON dmarc_reports (begin_epoch);

-- View: alignment failure summary
CREATE VIEW IF NOT EXISTS v_alignment_failures AS
SELECT
  r.org_name,
  dr.header_from,
  dr.source_ip,
  dr.spf_domain,
  dr.spf_aligned,
  dr.dkim_domain,
  dr.dkim_aligned,
  SUM(dr.message_count) AS failed_messages,
  COUNT(*)              AS record_count,
  MIN(r.begin_epoch)    AS first_seen,
  MAX(r.end_epoch)      AS last_seen
FROM dmarc_records dr
JOIN dmarc_reports r ON r.id = dr.report_id
WHERE dr.dmarc_result = 'fail'
GROUP BY r.org_name, dr.header_from, dr.source_ip, dr.spf_domain, dr.dkim_domain
ORDER BY failed_messages DESC;
```

## Worker — Alignment Monitoring Dashboard API

```typescript
// src/dmarc-dashboard.ts
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/dmarc/failures') {
      const since = Number(url.searchParams.get('since') ?? '0');
      const rows = await env.DB.prepare(`
        SELECT * FROM v_alignment_failures
        WHERE last_seen >= ?
        LIMIT 100
      `).bind(since).all();
      return Response.json(rows.results);
    }

    if (url.pathname === '/dmarc/pass-rate') {
      const rows = await env.DB.prepare(`
        SELECT
          header_from,
          SUM(CASE WHEN dmarc_result = 'pass' THEN message_count ELSE 0 END) AS passed,
          SUM(message_count) AS total,
          ROUND(100.0 * SUM(CASE WHEN dmarc_result = 'pass' THEN message_count ELSE 0 END)
                / SUM(message_count), 2) AS pass_rate_pct
        FROM dmarc_records
        GROUP BY header_from
        ORDER BY total DESC
      `).all();
      return Response.json(rows.results);
    }

    return new Response('Not found', { status: 404 });
  },
};
```

## Debugging Alignment Failures Step-by-Step

### Step 1: Identify the misaligned identifier

```bash
# Send a test message and inspect headers
dig TXT _dmarc.example.com          # check policy
dig TXT default._domainkey.example.com  # check DKIM public key

# Retrieve Authentication-Results header from received message
# Look for: spf=pass smtp.mailfrom=bounce@esp.com (note: not @example.com)
```

### Step 2: Fix SPF alignment — custom bounce domain

```
; DNS changes
bounce.example.com.  IN  MX  10  mta.esp-provider.com.
bounce.example.com.  IN  TXT "v=spf1 include:esp-provider.com ~all"
```

Configure your ESP to use `bounce.example.com` as the `MAIL FROM` domain. Now `org_domain(bounce.example.com) == org_domain(example.com)` satisfies relaxed SPF alignment.

### Step 3: Fix DKIM alignment — per-domain selector

Configure the ESP to sign with `d=example.com` or `d=mail.example.com`. Both satisfy relaxed alignment with `From: @example.com`. Publish the CNAME record the ESP provides:

```
esp._domainkey.example.com  CNAME  esp._domainkey.esp-provider.com.
```

### Step 4: Verify with email header analysis

Parse `Authentication-Results` from a received message:

```typescript
function parseAuthResults(header: string): Record<string, string> {
  const results: Record<string, string> = {};
  const spf  = header.match(/spf=(\w+)/)?.[1];
  const dkim = header.match(/dkim=(\w+)/)?.[1];
  const dmarc = header.match(/dmarc=(\w+)/)?.[1];
  if (spf)  results.spf  = spf;
  if (dkim) results.dkim = dkim;
  if (dmarc) results.dmarc = dmarc;
  return results;
}
```

## Mobile vs Desktop Email Rendering Considerations

Alignment failures manifest silently to end users — the message either never arrives or lands in spam without explanation. However, the monitoring tooling itself (alert emails, dashboard links) should be mobile-friendly:

- **Alert emails**: Single-column layout, bold source IP and domain names, colour-coded pass (green) / fail (red) status using inline styles only (Outlook strips `<style>` in mobile view).
- **Dashboard**: Responsive table with `overflow-x: auto` container; on mobile screens collapse low-priority columns (source IP, record count) using `display:none` under a media query.
- **Character width**: IPv6 source addresses are 39 characters; ensure `font-family: 'Courier New', monospace` and `word-break: break-all` in alert email cells.

## Anti-patterns

- **Checking authentication only, not alignment**: `spf=pass` in `Authentication-Results` does not mean DMARC will pass — alignment is a separate check.
- **Setting strict DMARC alignment (`aspf=s; adkim=s`) on day one**: many legitimate sending paths (ESP bounce handling, forwarded sub-domains) will fail strict alignment. Start with relaxed.
- **Ignoring `pct` < 100**: if your DMARC policy has `pct=10`, only 10 % of failing mail is rejected; the aggregate report still covers 100 % of mail. Do not interpret 90 % of failures as "passing".
- **Treating forensic (RUF) reports as alignment data**: RUF reports are per-message failure samples, not alignment aggregates. Use RUA for trend monitoring.
- **Parsing DMARC XML with regex alone**: the RFC 7489 schema allows arbitrary element ordering; use a real XML parser in production.

## Gotchas

- Google and Yahoo send RUA reports with gzip compression even when the spec allows plain XML. Always attempt gunzip before parsing.
- Some receivers (Outlook/Hotmail) send reports from `@microsoft.com` addresses — ensure the Email Routing rule covers the `dmarc-reports@` address and does not filter by sender.
- If `policy_pct` < 100 and you upgrade to `p=reject`, receivers apply rejection only to the sampled percentage. The DMARC aggregate report will continue to show failures for the non-sampled portion until `pct=100`.
- Sub-domain policy (`sp=`) applies to sub-domains not explicitly covered by their own DMARC record. An ESP sending from `bounce.example.com` with `sp=reject` will be rejected even if the `From:` is `@example.com` and alignment passes.

## Verification

```bash
# Check DMARC aggregate report ingestion
npx wrangler d1 execute DB --command \
  "SELECT COUNT(*), SUM(message_count), policy_domain
   FROM dmarc_records dr JOIN dmarc_reports r ON r.id = dr.report_id
   GROUP BY policy_domain;"

# Check alignment pass rate
curl https://your-worker.workers.dev/dmarc/pass-rate

# Manual alignment test
swaks --to test@mail-tester.com \
      --from you@example.com \
      --server smtp.esp.com \
      --auth-user you@example.com
# Then check mail-tester.com report for DMARC alignment result
```

## Related

- `dmarc-policy-setup.md`
- `dmarc-aggregate-report-analysis.md`
- `dmarc-rua-reporting.md`
- `spf-record-setup.md`
- `dkim-record-setup.md`
- `arc-chain-validation-and-trust-boundaries.md`
- `srs-sender-rewriting-scheme.md`

## Sources

- RFC 7489 — Domain-based Message Authentication, Reporting, and Conformance (DMARC)
- RFC 7208 — Sender Policy Framework
- RFC 6376 — DomainKeys Identified Mail (DKIM) Signatures
- Cloudflare Email Routing Workers — https://developers.cloudflare.com/email-routing/email-workers/
- DMARC.org alignment FAQ — https://dmarc.org/wiki/FAQ
