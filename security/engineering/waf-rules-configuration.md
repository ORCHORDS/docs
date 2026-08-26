# WAF Rules and Configuration

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application is exposed to the internet behind a CDN or load balancer but
has no Web Application Firewall (WAF). SQL injection, XSS, credential
stuffing, and bot abuse reach your origin servers directly. Or, you deployed a
WAF with default rules but it either blocks legitimate traffic (false
positives) or lets attacks through (false negatives).

## Context

A WAF inspects HTTP/S traffic at the application layer (L7) and blocks
attacks before they reach your application. In 2026, the three dominant WAF
platforms are Cloudflare WAF (edge-integrated, protection-per-dollar leader),
AWS WAF (cloud-native, deep AWS integration), and ModSecurity (open-source,
self-hosted). The correct approach is layered: managed rulesets for broad
coverage, custom rules for application-specific logic, rate limiting for
abuse, and bot management for automated threats.

## WAF rule types

### Managed rulesets (deploy first)
Pre-built rules maintained by the WAF vendor or OWASP community.

- **Cloudflare Managed Ruleset** — covers OWASP Top 10, CVE-specific rules,
  updated automatically. Enable in "block" mode after a log-only burn-in.
- **AWS Managed Rules** — AWS-maintained rule groups (Core, SQL injection,
  Linux/Windows OS, Known bad inputs). Enable via Web ACL.
- **OWASP CRS (Core Rule Set)** — open-source ruleset for ModSecurity.
  Version 4.x (2026) reduces false positives significantly vs. v3.

### Custom rules (application-specific)
Rules you write for your application's specific patterns.

```
# Cloudflare custom rule example: block non-API paths on API subdomain
(http.host eq "api.example.com" and not starts_with(http.request.uri.path, "/v1/"))
→ Action: Block

# AWS WAF custom rule: rate limit login endpoint
{
  "Name": "LoginRateLimit",
  "Statement": {
    "RateBasedStatement": {
      "Limit": 100,
      "AggregateKeyType": "IP",
      "ScopeDownStatement": {
        "ByteMatchStatement": {
          "SearchString": "/auth/login",
          "FieldToMatch": { "UriPath": {} },
          "PositionalConstraint": "EXACTLY"
        }
      }
    }
  },
  "Action": { "Block": {} }
}
```

### Rate limiting
Throttle by IP, API key, session, or geographic region. Essential for:
- Login/registration endpoints (credential stuffing)
- API endpoints (abuse, scraping)
- Resource-intensive endpoints (search, export)

### Bot management
Distinguish legitimate bots (Googlebot, monitoring) from malicious ones
(scrapers, credential stuffers). Cloudflare Bot Management uses ML scoring;
AWS WAF uses Bot Control managed rule group.

## Deployment workflow

1. **Log-only mode first** — deploy rules in "count" (AWS) or "log" (CF)
   mode for 7-14 days.
2. **Analyze false positives** — review blocked requests against legitimate
   traffic patterns. Whitelist known-good patterns.
3. **Enable blocking** — switch to "block" mode for rules with zero false
   positives in the burn-in period.
4. **Monitor continuously** — alert on sudden spikes in block rate (attack)
   or sudden drops (rule disabled/bypassed).
5. **Version control rules** — Terraform/Pulumi for AWS WAF, Cloudflare API
   or wrangler for CF rules. Never configure WAF rules only via UI.

## Anti-patterns

- **Deploy in block mode on day one** — you will block legitimate traffic.
  Always burn-in with logging first.
- **One WAF rule to rule them all** — a single "block SQLi" rule is not a
  WAF strategy. Layer managed + custom + rate limiting + bot management.
- **Ignoring the WAF after deployment** — attack patterns evolve. Review
  blocked traffic weekly. Update custom rules quarterly.
- **WAF as the only defense** — WAF is a layer, not the entire security
  stack. Input validation, parameterized queries, and CSP remain mandatory.
- **Overly broad IP blocking** — blocking entire country CIDRs blocks
  legitimate users behind shared IPs and VPNs.

## Gotchas

- **Request body inspection limits** — Cloudflare inspects the first 128 KB
  of the body; AWS WAF inspects the first 8 KB (64 KB with oversize
  handling). Attacks in larger payloads bypass body-based rules.
- **WebSocket traffic** — most WAFs only inspect the initial HTTP upgrade
  request, not subsequent WebSocket frames.
- **JSON/XML parsing** — ensure your WAF parses request bodies as structured
  data, not just string matching. SQLi in a JSON value may bypass string
  rules.
- **False positives on file uploads** — binary content in multipart/form-data
  often matches SQLi/XSS signatures. Exclude upload endpoints from body
  inspection rules.
- **Terraform drift** — if someone edits WAF rules via the console, your
  IaC state drifts. Use `terraform plan` to detect drift regularly.

## Verification

- **Simulated attacks** — test with OWASP ZAP, Nuclei, or manual SQLi/XSS
  payloads against a staging environment behind the WAF.
- **False positive rate** — monitor `WAF_BLOCK` events against legitimate
  user traffic. Target < 0.01% false positive rate.
- **Block rate dashboards** — track blocks by rule group, IP, path, and
  country. Spikes indicate attacks; drops indicate misconfiguration.
- **Bypass testing** — attempt WAF bypass techniques (encoding, chunked
  transfer, case variation) to verify rule robustness.

## Related

- `documentation/categories/security/owasp-top-10-2025.md`
- `documentation/categories/security/sql-injection-deep-dive.md`
- `documentation/categories/security/xss-deep-dive.md`
- `documentation/categories/security/rate-limiting-strategies.md`
- `documentation/categories/cloudflare/big-three-gotchas.md`

## Source URLs (verified 2026-08-16)

- WAF best practices 2026 — https://www.alessioligabue.it/en/blog/waf-best-practices
- AWS WAF security best practices 2026 — https://tocconsulting.fr/best-practices/waf-security
- Cloudflare WAF best practices — https://www.appsecure.security/blog/cloudflare-waf-best-practices
- Cloudflare custom rules docs — https://developers.cloudflare.com/waf/custom-rules/
- Cloudflare managed rules docs — https://developers.cloudflare.com/waf/managed-rules/
