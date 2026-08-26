# DMARC Aggregate Report Parsing with Cloudflare Email Routing + Workers

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Email providers (Google, Microsoft, Yahoo) send DMARC aggregate (rua) reports as XML attachments to a designated email address. You need to receive these automatically, parse the XML, persist the results, and surface pass/fail trends — all without standing up a dedicated server.

## Context

Cloudflare Email Routing can forward inbound email to a Worker via the `email` event. DMARC aggregate reports arrive as RFC 5322 messages with a gzip- or zip-compressed XML attachment. The Worker extracts and decompresses the attachment, parses the XML, stores per-record results in D1, and exposes a compliance trend HTTP endpoint. A high failure-rate alert is sent via MailChannels.

## Solution

### D1 Schema

```sql
-- migrations/0002_dmarc.sql
CREATE TABLE IF NOT EXISTS dmarc_reports (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id       TEXT NOT NULL UNIQUE,
  org_name        TEXT NOT NULL,
  email           TEXT NOT NULL,
  date_begin      INTEGER NOT NULL,
  date_end        INTEGER NOT NULL,
  received_at     INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS dmarc_records (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id       TEXT NOT NULL REFERENCES dmarc_reports(report_id),
  source_ip       TEXT NOT NULL,
  count           INTEGER NOT NULL,
  disposition     TEXT NOT NULL,  -- none | quarantine | reject
  dkim_result     TEXT NOT NULL,  -- pass | fail
  spf_result      TEXT NOT NULL,  -- pass | fail
  header_from     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_records_report
  ON dmarc_records (report_id);
CREATE INDEX IF NOT EXISTS idx_records_header_from
  ON dmarc_records (header_from, dkim_result, spf_result);
```

### Worker – Email Handler

```typescript
// src/dmarc-email-handler.ts
import { Env }         from './types';
import { parseDmarc }  from './dmarc-parser';
import { sendAlert }   from './alert';

export default {
  async email(message: ForwardableEmailMessage, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(handleDmarcEmail(message, env));
  },

  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    if (url.pathname === '/dmarc/compliance') return complianceTrend(env, url);
    return new Response('Not found', { status: 404 });
  },
};

async function handleDmarcEmail(
  message: ForwardableEmailMessage,
  env: Env
): Promise<void> {
  // Read the raw RFC 5322 message
  const raw     = await new Response(message.raw).arrayBuffer();
  const decoded = new TextDecoder().decode(raw);

  // Extract the compressed XML attachment
  const xmlBytes = extractAttachment(decoded);
  if (!xmlBytes) {
    console.warn('DMARC email received but no attachment found');
    return;
  }

  // Decompress (DMARC reports are gzip or zip)
  const xml = await decompressAttachment(xmlBytes);

  // Parse the XML
  const report = parseDmarc(xml);

  // Persist
  await persistReport(env, report);

  // Check failure rate
  const failRate = await getFailureRate(env, report.policyPublished.domain);
  if (failRate > 0.1) {
    await sendAlert(
      env,
      `DMARC failure rate for ${report.policyPublished.domain} is ${(failRate * 100).toFixed(1)}%`
    );
  }
}

function extractAttachment(rawEmail: string): Uint8Array | null {
  // Locate base64-encoded attachment block between MIME boundaries
  const boundaryMatch = rawEmail.match(/boundary="([^"]+)"/);
  if (!boundaryMatch) return null;
  const boundary = boundaryMatch[1];

  const parts = rawEmail.split('--' + boundary);
  for (const part of parts) {
    if (
      part.includes('application/gzip') ||
      part.includes('application/zip') ||
      part.includes('application/octet-stream')
    ) {
      const b64 = part.split(/\r?\n\r?\n/)[1]?.replace(/\s/g, '');
      if (!b64) continue;
      const binary = atob(b64);
      const bytes  = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes;
    }
  }
  return null;
}

async function decompressAttachment(bytes: Uint8Array): Promise<string> {
  // Workers DecompressionStream supports 'gzip' and 'deflate'
  const ds     = new DecompressionStream('gzip');
  const writer = ds.writable.getWriter();
  const reader = ds.readable.getReader();

  writer.write(bytes);
  writer.close();

  const chunks: Uint8Array[] = [];
  let done = false;
  while (!done) {
    const { value, done: d } = await reader.read();
    if (value) chunks.push(value);
    done = d;
  }

  const total  = chunks.reduce((s, c) => s + c.length, 0);
  const merged = new Uint8Array(total);
  let offset   = 0;
  for (const c of chunks) { merged.set(c, offset); offset += c.length; }

  return new TextDecoder().decode(merged);
}
```

### DMARC XML Parser

```typescript
// src/dmarc-parser.ts
// Uses Workers built-in HTMLRewriter in XML mode (tag-stream parsing)
export interface DmarcReport {
  reportMetadata:  ReportMetadata;
  policyPublished: PolicyPublished;
  records:         DmarcRecord[];
}

export interface ReportMetadata {
  orgName:   string;
  email:     string;
  reportId:  string;
  dateBegin: number;
  dateEnd:   number;
}

export interface PolicyPublished {
  domain: string;
  p:      string;
}

export interface DmarcRecord {
  sourceIp:    string;
  count:       number;
  disposition: string;
  dkim:        string;
  spf:         string;
  headerFrom:  string;
}

export function parseDmarc(xml: string): DmarcReport {
  // Simple regex-based extraction — sufficient for DMARC rua schema
  const get  = (tag: string) => xml.match(new RegExp(`<${tag}>([^<]*)</${tag}>`))?.[1] ?? '';
  const getN = (tag: string) => parseInt(get(tag), 10);

  const recordBlocks = [...xml.matchAll(/<record>([\s\S]*?)<\/record>/g)];
  const records: DmarcRecord[] = recordBlocks.map(([, block]) => {
    const rb  = (t: string) => block.match(new RegExp(`<${t}>([^<]*)</${t}>`))?.[1] ?? '';
    return {
      sourceIp:    rb('source_ip'),
      count:       parseInt(rb('count'), 10),
      disposition: rb('disposition'),
      dkim:        rb('dkim') || rb('result'),  // varies by reporter
      spf:         rb('spf'),
      headerFrom:  rb('header_from'),
    };
  });

  return {
    reportMetadata: {
      orgName:   get('org_name'),
      email:     get('email'),
      reportId:  get('report_id'),
      dateBegin: getN('date_begin'),
      dateEnd:   getN('date_end'),
    },
    policyPublished: {
      domain: get('domain'),
      p:      get('p'),
    },
    records,
  };
}
```

### Persistence and Trend

```typescript
// src/dmarc-db.ts
import { Env }        from './types';
import { DmarcReport } from './dmarc-parser';

export async function persistReport(env: Env, r: DmarcReport): Promise<void> {
  const m = r.reportMetadata;
  await env.DB.prepare(`
    INSERT OR IGNORE INTO dmarc_reports
      (report_id, org_name, email, date_begin, date_end)
    VALUES (?, ?, ?, ?, ?)
  `).bind(m.reportId, m.orgName, m.email, m.dateBegin, m.dateEnd).run();

  const stmts = r.records.map(rec =>
    env.DB.prepare(`
      INSERT INTO dmarc_records
        (report_id, source_ip, count, disposition, dkim_result, spf_result, header_from)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(m.reportId, rec.sourceIp, rec.count, rec.disposition, rec.dkim, rec.spf, rec.headerFrom)
  );
  await env.DB.batch(stmts);
}

export async function getFailureRate(env: Env, domain: string): Promise<number> {
  const { results } = await env.DB.prepare(`
    SELECT
      SUM(r.count)                                               AS total,
      SUM(CASE WHEN r.dkim_result='fail' AND r.spf_result='fail'
               THEN r.count ELSE 0 END)                        AS failed
    FROM dmarc_records  r
    JOIN dmarc_reports  rp ON rp.report_id = r.report_id
    WHERE r.header_from = ?
      AND rp.date_begin > unixepoch() - 86400 * 7
  `).bind(domain).all<{ total: number; failed: number }>();

  const { total, failed } = results[0];
  return total > 0 ? failed / total : 0;
}

export async function complianceTrend(
  env: Env,
  url: URL
): Promise<Response> {
  const domain = url.searchParams.get('domain') ?? '';
  const days   = Math.min(parseInt(url.searchParams.get('days') ?? '30', 10), 90);

  const { results } = await env.DB.prepare(`
    SELECT
      date(rp.date_begin, 'unixepoch') AS day,
      SUM(r.count)                     AS total,
      SUM(CASE WHEN r.dkim_result='pass' OR r.spf_result='pass'
               THEN r.count ELSE 0 END) AS compliant
    FROM dmarc_records  r
    JOIN dmarc_reports  rp ON rp.report_id = r.report_id
    WHERE r.header_from = ?
      AND rp.date_begin > unixepoch() - 86400 * ?
    GROUP BY day
    ORDER BY day
  `).bind(domain, days).all();

  return Response.json(results);
}
```

### Email Routing Configuration

In the Cloudflare dashboard, add an Email Routing rule:

- **Match**: `To address` = `dmarc-reports@yourdomain.com`
- **Action**: Send to Worker → `dmarc-email-handler`

Then in your DNS, set:
```
_dmarc.yourdomain.com TXT "v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@yourdomain.com"
```

## Implementation Details

- **MIME parsing**: The attachment extraction uses a simple boundary split. For production use, consider a more robust MIME parser if senders include unusual encoding (quoted-printable, non-standard boundaries).
- **Decompression**: Workers support `DecompressionStream` for gzip/deflate natively. Zip files (common from Yahoo/Microsoft) require a JS zip library bundled into the Worker.
- **INSERT OR IGNORE** on `dmarc_reports` ensures idempotency — the same report can be re-delivered without creating duplicates.
- **D1 batch** for records avoids N individual round-trips.
- **Failure rate threshold** of 10% is a conservative starting point; tune based on your sending volume and policy.

## Anti-patterns

- Do not parse the DMARC XML with `eval` or untrusted JSON deserialisers; use explicit field extraction.
- Do not store the raw XML blob in D1 — it can be megabytes; extract only the fields you need.
- Do not send alert emails synchronously inside the `email` event handler; use `ctx.waitUntil` or a Queue.
- Do not skip `INSERT OR IGNORE` / unique constraint on `report_id` — providers sometimes re-deliver reports.

## Gotchas

- The `email` event in Workers is only available when Email Routing is enabled and the Worker is bound as a destination.
- `ForwardableEmailMessage.raw` is a `ReadableStream` — read it exactly once.
- Some reporters (Yahoo) send zip archives, not gzip; `DecompressionStream('gzip')` will throw. Detect by MIME type or file extension.
- DMARC report XML schema varies slightly between senders (field order, optional `<reason>` elements). Always use safe defaults.
- D1 does not support `RETURNING` in all versions; avoid relying on it for the inserted row ID.

## Verification

```bash
# Deploy
npx wrangler deploy

# Send a test DMARC report email to your routing address (use an SMTP tool)
# Then query D1
npx wrangler d1 execute digest-db \
  --command "SELECT * FROM dmarc_reports ORDER BY received_at DESC LIMIT 5"

# Check compliance trend
curl "https://<worker>.workers.dev/dmarc/compliance?domain=yourdomain.com&days=7"

# Expected: JSON array of { day, total, compliant } rows
```

## Related

- `documentation/docs/policies/email/mailchannels-dkim-workers.md`
- `documentation/docs/policies/email/email-routing-catch-all.md`
- `documentation/docs/policies/email/workers-inbound-email-parser-routing.md`

## Sources

- https://developers.cloudflare.com/email-routing/email-workers/
- https://datatracker.ietf.org/doc/html/rfc7489 (DMARC)
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/streams/
