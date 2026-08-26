# pci-dss-v4-saas

**Issue:** Scoping and implementing PCI DSS v4.0 requirements for a SaaS platform that handles or passes through cardholder data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PCI DSS v4.0 became the only active standard on 31 March 2024. SaaS companies often assume that using Stripe or Braintree makes them "out of scope" — but scope depends on how card data flows. If your frontend ever touches the PAN (Primary Account Number), or if your servers are in the same network segment as card processing, you are in scope for at least some requirements.

## Pattern / Solution
**Scope reduction strategy — descoping via redirect/iframe:**

The least-scope architecture: never let cardholder data touch your servers.

```
User browser → Stripe.js / Braintree hosted fields (iframe served from PSP's domain)
                          ↓
               PSP tokenises PAN server-side
                          ↓
               Your server receives only a token (e.g., tok_...) → never a PAN
```

With this model your SAQ (Self-Assessment Questionnaire) is SAQ A — the simplest. You answer 22 requirements instead of 300+.

**Requirement mapping for SaaS (SAQ A-EP or SAQ D if any PAN touches your JS):**

| Req | Requirement | SaaS implementation |
|---|---|---|
| 2.2 | System components are hardened | CIS Benchmark for EC2/containers; disable unused services |
| 3.3 | Sensitive auth data not stored after auth | Never log CVV; validate in PSP; PAN not stored |
| 4.2.1 | Strong crypto for PAN in transit | TLS 1.2+ enforced; HSTS; no TLS 1.0/1.1 |
| 6.3 | Security vulnerabilities identified | CVSS-scored scan; critical patches ≤1 month |
| 6.4.3 | Payment page scripts managed and authorised | Explicit allowlist of all JS loaded on payment page; SRI hashes |
| 8.3.6 | Passwords meet complexity requirements | Min 12 chars, complexity enforced in IdP |
| 10.7.2 | Failures of critical controls detected | SIEM alerts on IDS/firewall failures |
| 11.6.1 | Change and tamper detection for payment pages | File integrity monitoring or CSP reporting for payment page |

**New v4.0 requirement — 6.4.3 and 11.6.1 (effective March 2025):**
All scripts on payment pages must be inventoried with authorisation and integrity validation (SRI). Implement a Content Security Policy with `script-src` limited to known hashes:

```html
<script
  src="https://js.stripe.com/v3/"
  integrity="sha384-<hash>"
  crossorigin="anonymous">
</script>
```

And enforce CSP reporting to detect injections:
```
Content-Security-Policy-Report-Only: script-src 'self' https://js.stripe.com; report-uri /csp-report
```

## Gotchas
- SAQ A is only valid if your payment page is **entirely** hosted by the PSP (redirect or full iframe). If your own JS touches the payment form — even just to read field values — you need SAQ A-EP or SAQ D.
- Storing the last 4 digits and expiry is permitted; storing CVV in any form (including logs) is a critical violation.
- v4.0 introduced "customised approach" — large merchants can substitute controls if they can demonstrate equivalent protection; for most SaaS this is not worth pursuing.
- Quarterly ASV (Approved Scanning Vendor) scans are required for external-facing IPs — schedule these; they cannot be retroactively run.
- Your PSP's PCI compliance does not extend to your cardholder data environment; each entity maintains its own compliance.

## Related
- `pci-dss-v4.md`
- `pci-dss-4.md`
- `pci-dss-tokenization-deep-dive-2026.md`
- `penetration-testing-scope.md`
