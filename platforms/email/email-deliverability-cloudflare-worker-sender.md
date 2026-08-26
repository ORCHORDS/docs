# email-deliverability-cloudflare-worker-sender

**Issue:** Deliverability failures when sending email through Cloudflare
           Workers via third-party SMTP or Email Workers—SPF misalignment,
           missing DKIM, and reputation blind spots
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Emails sent from a Cloudflare Worker arrive in spam or are silently
rejected.  Google Postmaster shows elevated spam rates even though
content looks clean.  DMARC reports reveal SPF alignment failures
because the envelope sender (`Return-Path`) domain does not match
the `From:` header domain.

## Context

Cloudflare Workers can dispatch email two ways: (1) via Cloudflare
Email Workers (send via `env.EMAIL`) which routes through Cloudflare's
own MTA, and (2) via a third-party HTTP API (Resend, SendGrid, SES).
In either path the Worker is not the MTA—the sending IP belongs to
Cloudflare or the ESP.  SPF must authorise those IPs; DKIM must be
signed by a key under your domain; DMARC must see alignment between
the RFC5321 `MAIL FROM` domain and the RFC5322 `From:` domain.

## SPF alignment in Workers

SPF aligns when the envelope sender (Return-Path) domain matches
the From: header domain.  ESPs use their own Return-Path subdomain
by default, which breaks DMARC alignment.

```
┌─────────────────────────────┬──────────────────────────────┐
│ Scenario                    │ SPF alignment result         │
├─────────────────────────────┼──────────────────────────────┤
│ ESP default Return-Path     │ FAIL — misaligned domain     │
│ Custom Return-Path subdomain│ PASS — must add ESP include  │
│ Cloudflare Email Workers    │ Requires custom domain setup │
└─────────────────────────────┴──────────────────────────────┘
```

Configure a custom Return-Path subdomain (e.g. `bounce.example.com`)
in your ESP's domain settings.  Then add the ESP's SPF include to
`bounce.example.com`, not the root domain:

```dns
bounce.example.com. IN TXT "v=spf1 include:sendgrid.net ~all"
```

Keep the root `example.com` SPF record separate and short to avoid
the 10-DNS-lookup limit.

## DKIM signing in Workers

Workers cannot sign DKIM inline—signing happens at the MTA layer.
For ESP-dispatched email, the ESP signs with a DKIM key scoped to
your sending domain; you publish the public key as a DNS TXT record.

```bash
# SendGrid: add domain in settings, retrieve CNAME records
# Resend: go to Domains, add DKIM CNAME
# Both provide CNAME-based rotation rather than raw TXT keys
```

For Cloudflare Email Workers (`send` binding):

```toml
# wrangler.toml
[[send_email]]
name = "EMAIL"
default_from = "noreply@example.com"
```

```js
export default {
  async fetch(req, env) {
    await env.EMAIL.send({
      from: { email: 'noreply@example.com', name: 'Example' },
      to:   [{ email: req.headers.get('X-To') }],
      subject: 'Verification',
      html: '<p>Your code: 123456</p>',
    });
    return new Response('sent');
  },
};
```

Cloudflare signs with a DKIM key under `example.com` once the
sending domain is verified in the Email Routing dashboard.

## Reputation monitoring

Monitor at both the IP and domain reputation layers.  Workers send
from ESP or Cloudflare IPs you do not control, so domain reputation
is the primary lever.

```
┌──────────────────────────┬───────────────────────────────┐
│ Signal                   │ Tool / endpoint               │
├──────────────────────────┼───────────────────────────────┤
│ Domain spam rate         │ Google Postmaster Tools       │
│ IP reputation            │ Microsoft SNDS                │
│ DMARC aggregate reports  │ rua= address in DMARC record  │
│ Bounce rate              │ ESP dashboard / webhooks      │
│ Complaint rate           │ ESP feedback loop (FBL)       │
└──────────────────────────┴───────────────────────────────┘
```

Keep hard bounce rate below 2 % and complaint rate below 0.1 %.
Parse DMARC aggregate XML reports weekly to catch new alignment
failures before ISPs act on them.

## Mobile email client rendering differences

Mobile clients parse authentication headers and render differently.

```
┌──────────────────┬────────────────────────────────────────┐
│ Client           │ Deliverability-relevant behaviour       │
├──────────────────┼────────────────────────────────────────┤
│ Gmail (Android)  │ Shows "via sendgrid.net" warning when  │
│                  │ SPF/DKIM domains mismatch From:        │
│ iOS Mail         │ Hides external warnings; users miss    │
│                  │ phishing cues—keep From: domain clean  │
│ Outlook Mobile   │ Strict DMARC enforcement; p=reject     │
│                  │ causes silent drops at O365 gateway    │
│ Samsung Mail     │ Uses Android system DNS; SPF lookups   │
│                  │ occasionally time out on slow networks │
└──────────────────┴────────────────────────────────────────┘
```

Set `p=quarantine` during ramp-up and promote to `p=reject` only
after Postmaster shows 0 % spam rate for 30 days.

## Anti-patterns

- Publishing `+all` in SPF to "fix" failures—authorises all senders
  worldwide and makes SPF meaningless.
- Using the ESP's default subdomain Return-Path without adding a
  custom bounce domain, then wondering why DMARC shows SPF failures.
- Rotating DKIM keys by deleting the old DNS record before the ESP
  has fully switched—causes a gap where active messages fail DKIM.
- Sending from a brand-new domain with no warm-up history; even
  perfect authentication cannot overcome zero domain age reputation.
- Ignoring DMARC `ruf` forensic reports because they contain PII—
  at minimum parse `rua` aggregate reports for alignment data.

## Gotchas

- Cloudflare Email Workers `send` binding requires the sending
  domain to be on Cloudflare with Email Routing enabled, even if
  email routing (inbound) is not used—it is needed to verify the
  domain for outbound DKIM.
- SPF has a 10-DNS-lookup limit.  `include:` chains from ESPs
  often themselves contain several lookups.  Use `spfcheck.org`
  to count lookups before deploying.
- DMARC alignment is strict by default (`aspf=s`).  A subdomain
  sender (`mail.example.com`) fails alignment against a From:
  header of `example.com` under strict mode.  Set `aspf=r` for
  relaxed unless you control every subdomain.

## Verification

```bash
# Check SPF, DKIM, DMARC alignment on a live message
# Send a test to mail-tester.com and review the report

# Verify SPF record lookup count
dig +short TXT example.com | grep spf

# Confirm DKIM public key is published
dig +short TXT <selector>._domainkey.example.com

# Fetch DMARC record
dig +short TXT _dmarc.example.com

# Check Google Postmaster domain reputation
# Visit: https://postmaster.google.com
# Threshold: domain reputation = High before ramping volume
```

## Related

- `documentation/categories/email/dkim-record-setup.md`
- `documentation/categories/email/spf-record-setup.md`
- `documentation/categories/email/dmarc-policy-setup.md`
- `documentation/categories/email/cloudflare-email-routing-workers.md`
- `documentation/categories/email/ip-warming-domain-reputation-deliverability.md`

## Source URLs

- https://developers.cloudflare.com/email-routing/email-workers/
- https://developers.cloudflare.com/email-routing/setup/
- https://datatracker.ietf.org/doc/html/rfc7489  (DMARC)
- https://postmaster.google.com/
- https://sendersupport.olc.protection.outlook.com/snds/
