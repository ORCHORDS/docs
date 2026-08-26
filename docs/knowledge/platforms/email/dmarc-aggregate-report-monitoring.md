# DMARC Aggregate Reports — Parsing, Monitoring, and Enforcement

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

You deployed DMARC with `p=none` six months ago but never looked at
the aggregate reports. Your `rua` mailbox has 10,000 unread XML
reports. You have no idea which services send email on behalf of your
domain, whether SPF and DKIM are properly aligned, or whether anyone is
spoofing your domain. Legal wants to move to `p=reject` to stop phishing,
but you cannot do that safely without understanding your current email
sources.

## Context

DMARC (Domain-based Message Authentication, Reporting, and Conformance)
aggregate reports (RUA) are XML files sent by receiving mail servers
to the address specified in your domain's DMARC record (`rua=` tag).
Each report contains authentication results (SPF, DKIM, alignment) for
emails claiming to be from your domain, grouped by source IP and
sending domain. In 2026, aggregate reports are the primary feedback
mechanism for DMARC compliance — they do not contain message content or
PII, making them safe for global data privacy compliance. The standard
path is: deploy `p=none` → analyze reports for 4-8 weeks → identify
and fix all legitimate senders → move to `p=quarantine` → then
`p=reject`.

## DMARC record structure

```
_dmarc.example.com TXT "v=DMARC1; p=none; rua=mailto:dmarc@example.com;
  ruf=mailto:forensics@example.com; pct=100; adkim=r; aspf=r; fo=1"

Tags:
  v=DMARC1     Version (required)
  p=           Policy: none | quarantine | reject
  rua=         Aggregate report recipient (mailto: or https:)
  ruf=         Forensic report recipient (rarely sent in 2026)
  pct=         Percentage of messages to apply policy (1-100)
  adkim=       DKIM alignment: r (relaxed) | s (strict)
  aspf=        SPF alignment: r (relaxed) | s (strict)
  fo=          Forensic report options: 0|1|d|s
```

## Report XML structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <report_metadata>
    <org_name>google.com</org_name>
    <date_range>
      <begin>1723766400</begin>
      <end>1723852799</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <p>none</p>
    <adkim>r</adkim>
    <aspf>r</aspf>
  </policy_published>
  <record>
    <row>
      <source_ip>198.51.100.1</source_ip>
      <count>1523</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
      </dkim>
      <spf>
        <domain>example.com</domain>
        <result>pass</result>
      </spf>
    </auth_results>
  </record>
</feedback>
```

## Parsing with parsedmarc

```bash
# Install parsedmarc (Python, open source)
pip install parsedmarc

# Parse reports from mailbox (IMAP)
parsedmarc --imap-host imap.example.com \
           --imap-user dmarc@example.com \
           --imap-password $IMAP_PASSWORD \
           --elasticsearch-hosts http://localhost:9200

# Parse local XML/ZIP files
parsedmarc -o json /path/to/reports/

# Output to CSV for spreadsheet analysis
parsedmarc -o csv /path/to/reports/ > dmarc_results.csv
```

## Monitoring dashboard (key metrics)

```
Track daily/weekly:
  → Total emails reported (volume by source IP)
  → DKIM pass rate (target: >99% for known senders)
  → SPF pass rate (target: >99% for known senders)
  → Alignment pass rate (SPF + DKIM aligned)
  → Unknown sources (IPs not in your known sender list)
  → Policy override count (forwarding, mailing lists)

Known sender inventory:
  Source IP       Service          SPF   DKIM   Status
  198.51.100.1    SendGrid         pass  pass   ✓ Authorized
  203.0.113.5     Mailchimp        pass  pass   ✓ Authorized
  192.0.2.10      Unknown          fail  fail   ✗ Investigate
  198.51.100.50   Salesforce       pass  fail   ⚠ Fix DKIM

Enforcement readiness checklist:
  □ All legitimate senders identified
  □ All senders pass SPF + DKIM alignment
  □ Pass rate >95% across all reports
  □ Unknown sources investigated and resolved
  □ Forwarding/mailing list overrides understood
```

## Enforcement progression

```
Phase 1: Monitor (4-8 weeks)
  p=none; rua=mailto:dmarc@example.com
  → Collect reports, identify all senders
  → Fix SPF records for all authorized senders
  → Configure DKIM signing for all authorized senders

Phase 2: Quarantine (2-4 weeks)
  p=quarantine; pct=10; rua=mailto:dmarc@example.com
  → Start at 10%, increase to 25%, 50%, 100%
  → Monitor for legitimate email being quarantined
  → Fix any newly discovered senders

Phase 3: Reject
  p=reject; rua=mailto:dmarc@example.com
  → Spoofed email is rejected by receiving servers
  → Continue monitoring for new senders
  → Eligible for BIMI (brand logo in email clients)
```

## Anti-patterns

- **Deploying p=reject without monitoring** — skipping the
  `p=none` monitoring phase and going straight to reject. This
  blocks legitimate email from services you forgot about (marketing
  tools, CRM, ticketing systems). Always monitor first.
- **Ignoring aggregate reports** — setting up `rua=` but never
  parsing the reports. Reports are the only way to discover
  unauthorized senders and verify that legitimate senders pass
  authentication.
- **Manual XML parsing** — reading raw DMARC XML files by hand.
  Use automated tools (parsedmarc, Postmark DMARC, dmarcian) to
  parse, aggregate, and visualize report data.
- **Single rua recipient** — sending reports to only one mailbox
  that is not monitored. Use a dedicated monitoring service or
  multiple `rua` recipients for redundancy.

## Gotchas

- **Report delivery is not guaranteed** — receiving servers send
  reports voluntarily. Not all mail servers send DMARC reports,
  and some send them infrequently. You may not see reports from
  smaller mail providers.
- **Forwarded email fails SPF** — when email is forwarded (mailing
  lists, auto-forwarding), the forwarding server's IP replaces the
  original sender's IP, causing SPF to fail. DKIM survives
  forwarding if the message body is not modified. This is why DKIM
  alignment is more important than SPF alignment.
- **Report size limits** — large domains may generate reports with
  millions of records. Some providers compress reports (gzip/zip),
  and some split into multiple reports. Ensure your parser handles
  compressed and multi-part reports.
- **Subdomain policy inheritance** — without `sp=` (subdomain
  policy), subdomains inherit the parent domain's DMARC policy.
  If you set `p=reject` on `example.com`, it applies to
  `mail.example.com` unless you set a separate DMARC record.

## Verification

- DMARC record is published with `rua=` pointing to a monitored address.
- Aggregate reports are parsed automatically (daily or weekly).
- All legitimate email sources are identified and authorized.
- SPF and DKIM alignment pass rate exceeds 95%.
- Enforcement progression plan is documented and followed.
- Unknown sources are investigated within 48 hours.

## Related

- `documentation/docs/policies/email/spf-dkim-dmarc-authentication.md`
- `documentation/docs/policies/email/ip-warming-domain-reputation-deliverability.md`
- `documentation/docs/policies/email/bimi-brand-indicators-email.md`

## Source URLs (verified 2026-08-16)

- The Complete DMARC Best Practices Guide for 2026 — https://easydmarc.com/blog/dmarc-best-practices/
- DMARC Aggregate Reports Explained 2026 — https://emailverifierapi.com/blog/dmarc-aggregate-reports-explained/
- DMARC Reports: How To Read, Interpret & Act On Them — https://powerdmarc.com/how-to-read-dmarc-reports/
- DMARC Report Parsers Compared — https://mailflowauthority.com/email-authentication/dmarc-report-parsers
