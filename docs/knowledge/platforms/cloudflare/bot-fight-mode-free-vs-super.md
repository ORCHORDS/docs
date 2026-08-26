# bot-fight-mode-free-vs-super

**Issue:** A free-plan Cloudflare zone has Bot Fight Mode enabled and suddenly legitimate automated traffic breaks: uptime monitors get challenged, payment-processor webhook callbacks fail, and partner API calls are blocked. There is no rule, exception, or skip action that fixes it, because Bot Fight Mode (free) is deliberately not extensible. The operator needs to understand exactly what Bot Fight Mode does on the free tier, what Super Bot Fight Mode (SBFM, Pro+) adds, and the decision path between "turn it off", "carve exceptions after upgrading", and "live with it".

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Bot Fight Mode (Free plan) actually does

1. **Pattern-based detection, domain-wide.** Bot Fight Mode identifies requests matching known bot patterns and issues computationally expensive challenges to them, raising the cost of automated abuse. It applies to the entire domain with "no endpoint restrictions" — there is no per-path scoping.
2. **Issues challenges, not blocks.** The free-tier behavior is to challenge matched bot traffic (CPU-intensive challenge). It cannot block-by-category; that distinction arrives with SBFM.
3. **Force-enabled JavaScript Detections.** With Bot Fight Mode, JavaScript Detections (an invisible script injected into HTML pages, stored via `cf_clearance`, feeding `cf.bot_management.js_detection.passed`) is "automatically enabled and cannot be disabled". It is injected on HTML responses only, not API/AJAX/mobile traffic.
4. **Verified bots are not your problem — your own automation is.** Cloudflare's own verified-bot list keeps Google/Bing crawlers working. The false positives on free plans come from *your* integrations: monitoring, health checks, CI, payment webhooks, mobile app backends.
5. **Dashboard location.** Security > Settings, filter by "Bot traffic", toggle "Bot fight mode". Verify it before blaming the WAF — it is a separate feature from custom rules and managed rules.

## Why you cannot carve exceptions on Free

1. **Not part of the Ruleset Engine.** Bot Fight Mode runs outside the Ruleset Engine phases, so WAF custom rules with a Skip action — the standard mechanism for exempting an IP or user agent — cannot bypass it. Skip options exist for rate limiting (`http_ratelimit`), SBFM (`http_request_sbfm`), and managed rules, but not for BFM.
2. **No path/host scoping.** No configuration rule, page rule, or per-hostname switch can limit where BFM applies.
3. **Only two remedies on Free.** Per Cloudflare's own docs: turn Bot Fight Mode off, or upgrade to Super Bot Fight Mode for granular control. There is no third option.
4. **Interaction with IP Access Rules is partial.** BFM can still trigger alongside IP Access Rules, though it will not fire if an IP Access rule matches the request first. Do not rely on this as an exception mechanism — it is not documented as a supported bypass.
5. **CSP friction from injected JS.** The injected detection script lives under `/cdn-cgi/challenge-platform/`; if you use Content-Security-Policy, allow that path. Nonces are supported, but only via the CSP response header — nonces declared in a `<meta>` tag are not.

## What Super Bot Fight Mode adds (Pro / Business / Enterprise)

1. **Configurable actions per bot category.** SBFM lets you choose separate actions for "definitely automated", "likely automated", and "verified bots" traffic, instead of BFM's blanket challenge.
2. **Skip-action exceptions.** Because SBFM runs on the Ruleset Engine (`http_request_sbfm` phase), a WAF custom rule with a Skip action can exempt specific IPs or user agents — the canonical fix for "SBFM is blocking my payment processor" is a custom rule matching `ip.src` or `http.user_agent` with Skip > All Super Bot Fight Mode rules.
3. **Static resource protection.** Optional protection extended to static-resource file types, configurable separately.
4. **JavaScript Detections becomes optional.** On SBFM (and Enterprise Bot Management) JS Detections is a toggle, not a mandate.
5. **Analytics.** The Bot Report shows bot traffic over the past 24 hours — limited, but far better than Free's near-zero visibility into what BFM challenged.
6. **Enterprise nuance.** Enterprise accounts *without* the Bot Management add-on get "Super Bot Fight Mode for Business". The full `cf.bot_management.score` field, ML scoring, and per-path thresholds require the Bot Management add-on — path-specific bot thresholds on an API are impossible below that tier.

## Operational gotchas when moving from BFM to SBFM

1. **Turn BFM off first.** When upgrading, explicitly disable Bot Fight Mode in Security > Settings before enabling SBFM; they are separate toggles and should not both be active.
2. **Cloudflare Tunnel + SBFM = broken tunnels.** If you use Cloudflare Tunnel, keep "Definitely automated" set to Allow in SBFM, otherwise tunnel connections fail with `websocket: bad handshake`.
3. **WordPress loopback requests.** WordPress Site Health makes loopback requests that bot detection can block. SBFM has an "Optimize for WordPress" toggle that authorizes those loopbacks; BFM (free) has no equivalent.
4. **Custom rules run before SBFM.** A terminating action (block/challenge) in a custom rule prevents SBFM from evaluating that request — useful to know when debugging why a request was blocked "twice" or not at all.
5. **SBFM is still domain-wide.** SBFM does not support path-specific thresholds either; it just supports exceptions. True per-path bot-score logic is Bot Management (Enterprise add-on).

## Related

- `free-tier-domain-security-runbook.md` — how BFM fits into the overall free-tier security posture alongside the toggles and IP Access Rules.
- `under-attack-mode-ddos-runbook.md` — the other zone-wide "challenge everything" switch, and how it differs (temporary, emergency).
- `waf-best-practices.md` and `waf-managed-rules-exception-order-and-future-rule-drift.md` — Skip-action ordering and drift on the Ruleset Engine side.
- `turnstile-best-practices.md` — Turnstile as an application-layer alternative when zone-level bot toggles are too blunt.
