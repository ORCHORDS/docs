# dmarc-aggregate-report-analysis

**Issue:** Automating DMARC aggregate (rua) XML report processing,
           detecting alignment failures, and acting on escalation
           thresholds using Cloudflare Workers
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

DMARC aggregate reports arrive as gzip-compressed XML attachments,
often dozens per day from different receivers.  Manual review does
not scale.  Teams miss alignment regressions — especially from mobile
email clients that modify MIME structure — until complaint rates spike.

## Context

Receivers send aggregate reports to the `rua=` address in the DMARC
record once per UTC day.  Each report is a `<feedback>` XML document
describing per-source alignment results for the sending domain.  A
Workers-based pipeline can receive these reports via Email Routing,
parse the XML, store normalized records in D1 or KV, and trigger
alerts when failure rates exceed thresholds.

## XML structure and key fields

```xml
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <date_range><begin>1753056000</begin><end>1753142400</end></date_range>
    <report_id>12345678</report_id>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>quarantine</p>
    <pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>209.85.220.41</source_ip>
      <count>4203</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
      </dkim>
      <spf>
        <domain>bounces.esp.com</domain>
        <result>pass</result>  <!-- aligned to esp.com, not example.com -->
      </spf>
    </auth_results>
  </record>
</feedback>
```

Key fields to extract per record:

```
┌────────────────────────┬──────────────────────────────────────┐
│ Field                  │ Meaning                              │
├────────────────────────┼──────────────────────────────────────┤
│ source_ip              │ Sending server IP                    │
│ count                  │ Messages in this period              │
│ disposition            │ Policy applied (none/quarantine/     │
│                        │ reject)                              │
│ dkim (evaluated)       │ DKIM aligned with From: domain?      │
│ spf  (evaluated)       │ SPF  aligned with From: domain?      │
│ auth_results.spf.domain│ Envelope-From domain (may differ)    │
└────────────────────────┴──────────────────────────────────────┘
```

## Workers-based parsing pipeline

The Email Worker receives the rua report email, extracts the gzip
attachment, decompresses it, parses the XML, and upserts records
into D1.

```js
import { gunzipSync } from 'fflate';  // bundled; no external fetch

export default {
  async email(message, env, ctx) {
    // Collect raw message bytes
    const raw = await streamToBuffer(message.raw);
    const xml  = extractDmarcXml(raw);  // parse MIME, find attachment
    if (!xml) { message.setReject('No DMARC XML found'); return; }

    const report = parseDmarcXml(xml);
    await storReport(report, env.DB);
    await evalThresholds(report, env);
    await message.forward(env.ARCHIVE_ADDRESS);
  }
};

function parseDmarcXml(xmlStr) {
  // Use a minimal pull-parser; Workers lack DOMParser
  // Extract <record> blocks and parse key fields
  const records = [];
  for (const m of xmlStr.matchAll(/<record>([\s\S]*?)<\/record>/g)) {
    records.push({
      sourceIp:    extract(m[1], 'source_ip'),
      count:       parseInt(extract(m[1], 'count'), 10),
      disposition: extract(m[1], 'disposition'),
      dkim:        extract(m[1], 'dkim'),   // policy_evaluated
      spf:         extract(m[1], 'spf'),    // policy_evaluated
    });
  }
  return { orgName: extract(xmlStr, 'org_name'), records };
}

function extract(xml, tag) {
  const m = xml.match(new RegExp(`<${tag}>(.*?)</${tag}>`));
  return m ? m[1].trim() : '';
}
```

## Detecting alignment failures

A record **fails DMARC** when both `dkim=fail` AND `spf=fail` in
`policy_evaluated`.  A record passes when either aligns.  Track:

- **Failure rate**: `sum(count where dkim=fail AND spf=fail)` /
  `sum(count)` per reporting period.
- **Unknown sources**: IPs with no match in your ESP allowlist — these
  are either rogue senders or new legitimate sources not yet aligned.
- **Disposition mismatch**: Records where policy is `reject` but
  `disposition=none` — the receiver ignored your policy (rare but
  documented for large mailbox providers acting as forwarders).

```
┌────────────────────────────┬────────────┬──────────────────────┐
│ Scenario                   │ dkim eval  │ spf eval             │
├────────────────────────────┼────────────┼──────────────────────┤
│ ESP sends, DKIM aligned    │ pass       │ fail (env-from diff) │
│ Forwarder strips DKIM      │ fail       │ fail  → DMARC FAIL   │
│ Direct send, SPF aligned   │ fail       │ pass                 │
│ Spoofed send               │ fail       │ fail  → DMARC FAIL   │
└────────────────────────────┴────────────┴──────────────────────┘
```

## Mobile email client quirks in DMARC reports

Several mobile-related behaviors create noise in aggregate reports:

- **Gmail app auto-forwarding**: When a Gmail user has server-side
  forwarding enabled (not filtering), Gmail breaks DKIM on re-
  delivery and the original IP disappears; the rua report shows the
  Gmail forwarding server IP with both checks failing.  These are
  distinguishable by the source IP being in Google's ASN — tag these
  records and exclude from alignment-failure alerts.

- **Apple Mail iCloud relay**: iOS Mail's Hide My Email feature
  routes mail through Apple relay servers, which re-sign with Apple
  DKIM.  Your domain's DKIM may still pass if the signature survives,
  but `source_ip` will be an Apple relay, not your ESP.

- **Samsung Email app thread resurrection**: Older Samsung devices
  resend buffered drafts with stale DKIM timestamps past the 5-day
  validity window.  The rua report shows DKIM `fail` with a
  previously trusted IP — check `auth_results.dkim.result` for
  "fail" with known IPs to identify this pattern vs. genuine spoofs.

- **Mobile OOO replies in reports**: Auto-replies from mobile OOO
  handlers sometimes appear with the original From: domain in the
  `policy_evaluated` section, artificially boosting failure counts
  for that IP.

## Escalation thresholds

```
┌──────────────────────────────┬────────────────────────────────┐
│ Metric                       │ Action                         │
├──────────────────────────────┼────────────────────────────────┤
│ Failure rate > 5%            │ Notify on-call (Slack/PD)      │
│ Failure rate > 20%           │ Page immediately; consider     │
│                              │ rolling back p= to none        │
│ Unknown high-volume IP       │ Alert + manual investigation   │
│ (>100 messages, not in allow)│                                │
│ Spoof volume drops to 0      │ Confirm p=reject is working    │
│ after reject enforcement     │                                │
│ Disposition=none when p=rej  │ Log; receiver may be ignoring  │
│                              │ policy — no action required    │
└──────────────────────────────┴────────────────────────────────┘
```

Escalation Worker:

```js
async function evalThresholds(report, env) {
  const total   = report.records.reduce((s, r) => s + r.count, 0);
  const failed  = report.records
    .filter(r => r.dkim === 'fail' && r.spf === 'fail')
    .reduce((s, r) => s + r.count, 0);
  const rate    = total > 0 ? failed / total : 0;

  if (rate > 0.20) {
    await notify(env, 'CRITICAL', `DMARC failure ${(rate*100).toFixed(1)}%`);
  } else if (rate > 0.05) {
    await notify(env, 'WARNING',  `DMARC failure ${(rate*100).toFixed(1)}%`);
  }
}
```

## Anti-patterns

- Parsing `auth_results.spf.result` instead of
  `policy_evaluated.spf` — auth_results shows raw SPF outcome, not
  alignment; a passing SPF for a different domain still fails DMARC.
- Alerting on every single-message failure — spammers send one test
  message frequently; weight alerts by `count`, not record count.
- Treating all Gmail/Apple IPs as suspicious — they are legitimate
  forwarders; maintain an IP-range allowlist for known forwarder ASNs.
- Skipping decompression error handling — malformed reports arrive
  occasionally; a crash in the email Worker causes the report to be
  lost without an archive copy.

## Gotchas

- The `pct` field in `policy_published` tells you what the policy was
  at the time, not what it is now; policy could have changed between
  the reporting period and when you read the report.
- Reports from some receivers (Proofpoint, Mimecast) arrive as ZIP
  archives, not gzip; handle both `application/gzip` and
  `application/zip` MIME types in the Worker.
- `date_range.begin` and `date_range.end` are UTC epoch seconds, not
  milliseconds; multiply by 1000 before constructing a JS `Date`.
- Some receivers omit `<auth_results>` entirely if there are no
  results to report; always guard against missing elements.

## Verification

```bash
# Send a synthetic report to the rua address
cat tests/fixtures/dmarc-report-sample.xml \
  | gzip | base64 \
  | mail -s "Report Domain: example.com" \
         -a "Content-Type: application/gzip" \
         dmarc-agg@example.com

# Confirm the Worker processed it
wrangler tail --format pretty

# Query D1 for stored records
wrangler d1 execute MY_DB \
  --command "SELECT source_ip, SUM(count) as msgs,
             SUM(CASE WHEN dkim='fail' AND spf='fail'
                 THEN count ELSE 0 END) as failed
             FROM dmarc_records GROUP BY source_ip;"
```

## Related

- `documentation/categories/email/dmarc-policy-setup.md`
- `documentation/categories/email/dmarc-enforcement-staged-rollout.md`
- `documentation/categories/email/dmarc-rua-reporting.md`
- `documentation/categories/email/cloudflare-email-routing-workers.md`

## Source URLs

- https://datatracker.ietf.org/doc/html/rfc7489#section-7.2
- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/d1/
- https://dmarc.org/resources/dmarcfeedback/
