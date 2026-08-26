# waf-best-practices

**Issue:** Cloudflare WAF — custom rules, geo-restrictions
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your site is under attack. You see SQL injection
attempts in the logs. You see bot scrapers. You see
suspicious countries hitting your API. You need a
WAF.

## Root cause
**WAF rules protect at the edge.** Use CF WAF.

**Source:** CF WAF:
https://developers.cloudflare.com/waf/

## The "WAF" concept

The WAF is the network-level filter:
- **Custom rules:** Your rules
- **Managed rules:** CF's rules
- **Rate limit:** Per IP
- **Bot management:** Bot detection
- **DDoS protection:** Built-in

The WAF protects at the edge.

## The "custom rule" pattern

For a custom rule:
```
Field: http.request.uri.path
Operator: equals
Value: /api/signup
Action: Managed Challenge
```

The rule is created.

## The "rules language" pattern

For the expression:
```
(http.request.uri.path eq "/api/signup") and (ip.geoip.country in {"CN" "RU" "VN"})
```

The expression is the filter.

## The "actions" pattern

For actions:
- **Block:** Stop the request (high confidence)
- **Managed Challenge:** Smart CAPTCHA
- **JS Challenge:** Older CAPTCHA
- **Skip:** Bypass later rules
- **Log:** Don't act, just log

The action depends on confidence.

## The "rule order" pattern

For order:
- **Allow-list first:** Verified bots, partners
- **Block:** High confidence
- **Managed challenge:** Lower confidence
- **Log:** Last (catch-all)

Order matters; first match wins.

## The "geo-restriction" pattern

For geo:
```
(http.host eq "corporate.example.com") and not (ip.geoip.country in {"SA" "AE" "KW"})
```

The country is restricted.

## The "admin path" pattern

For admin paths:
```
(http.request.uri.path contains "/admin" or http.request.uri.path contains "/wp-admin") and not (ip.src in {1.2.3.0/24 5.6.7.0/24})
```

The admin is IP-allow-listed.

## The "scraper block" pattern

For scrapers:
```
(http.user_agent contains "HeadlessChrome") or (http.user_agent contains "scrapy") or (http.user_agent contains "Python-urllib")
```

The scraper is blocked.

## The "empty UA" pattern

For empty UA:
```
(http.user_agent eq "") and not (http.request.uri.path eq "/health")
```

The empty UA is blocked.

## The "AI bot" pattern

For AI bots:
```
(http.user_agent contains "GPTBot") or (http.user_agent contains "ClaudeBot") or (http.user_agent contains "anthropic-ai") or (http.user_agent contains "Bytespider") or (http.user_agent contains "CCBot")
```

The AI bot is blocked (or allowed).

## The "verified bot allow-list" pattern

For verified bots (ALWAYS at the top):
```
cf.client.bot
```
Action: **Skip remaining rules.**

The verified bot is allowed.

**Why first:** If you block first, Google loses search
rankings within a week.

## The "rate limit" pattern

For rate limit:
- **Per IP:** 100 req/min
- **Per endpoint:** 10 req/min for sensitive
- **Burst:** Allow

CF has built-in rate limiting.

## The "log first" pattern

For new rules, ALWAYS log first:
1. **Create rule** in log mode
2. **Wait 1-2 weeks:** Review Security Events
3. **Fix false positives:** Adjust
4. **Promote to block:** When confident

The log prevents false positives.

## The "common mistakes" pattern

Common mistakes to avoid:
1. **Block before verified-bot allow-list:** Lose SEO
2. **Forget to audit payment webhook IPs:** Reconciliation fails
3. **`contains` when `eq` is right:** Over-broad
4. **Skip the log period:** False positives
5. **No monitoring:** Don't know it's working

Mistakes are common; avoid them.

## The "WAF limits" pattern

For limits:
- **Free:** 5 rules
- **Pro:** 20 rules
- **Business:** 100 rules
- **Enterprise:** Custom

The rules are limited per plan.

## The "WAF + Worker" pattern

For WAF + Worker:
- **WAF:** Network-level (L7)
- **Worker:** App-level
- **Together:** Defense in depth

The defense is layered.

## The "WAF observability" pattern

For observability:
- **Block count:** Per rule
- **Challenge count:** Per rule
- **Top sources:** IPs + countries
- **Per rule:** Match count

The metrics are in the dashboard.

## The "WAF anti-pattern" anti-patterns

### 1. Block without log
- **Issue:** False positives
- **Fix:** Log first

### 2. No verified-bot allow-list
- **Issue:** Lose SEO
- **Fix:** Allow-list at top

### 3. `contains` over-broad
- **Issue:** Block too much
- **Fix:** Use `eq` when right

### 4. No payment webhook allow-list
- **Issue:** Reconciliation fails
- **Fix:** Allow-list payment provider IPs

### 5. Too many rules
- **Issue:** Performance
- **Fix:** Combine + prioritize

## Verification
- **Test:** Each rule matches
- **Test:** False positives are caught
- **Live:** Block count monitored
- **Audit:** Quarterly review

## Gotchas
- **The "block without log" anti-pattern.** Log first.
- **The "no allow-list" anti-pattern.** Allow-list
  first.
- **The "over-broad contains" anti-pattern.** Use `eq`.

## Related
- `cloudflare/turnstile-best-practices.md`
- `feature-cookbook-rate-limiting.md`
- `feature-cookbook-rate-limiting-detail.md`
- `feature-cookbook-monitoring.md`
- `feature-cookbook-incident-response.md`
- WAF: https://developers.cloudflare.com/waf/
- Rules language: https://developers.cloudflare.com/ruleset-engine/
