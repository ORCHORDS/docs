# bot-management-enterprise

**Issue:** An Enterprise zone with the Bot Management add-on needs to move from "the account team enabled it" to actually enforcing on bot scores: the team must understand how the 1–99 score is produced, which `cf.bot_management.*` fields exist (score, JA3/JA4 fingerprints, verified-bot flags, detection IDs), how verified bots and their categories work, how session/behavioral signals smooth or skew scores, and how to write and tune rules per path without breaking partner APIs and mobile apps. This article covers the Enterprise Bot Management mechanics only — the free/pro Bot Fight Mode vs Super Bot Fight Mode boundary is covered in `bot-fight-mode-free-vs-super.md`.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Enterprise Bot Management is (and is not)

1. **An Enterprise add-on, not a self-serve toggle.** Bot Management is "added to Enterprise plans by your account team" — there is no dashboard purchase path, and onboarding is done with a Solutions Engineering team. If a zone is entitled, it is enabled in Security → Settings → filter "Bot traffic" → Bot management.
2. **It replaces the lower-tier toggles.** Zones with Enterprise Bot Management show no Bot Fight Mode or Super Bot Fight Mode options at all — do not go looking for SBFM knobs there.
3. **What the subscription unlocks.** Granular 1–99 scores per request, JA3/JA4 fingerprints, bot tags, detection IDs, dedicated Bot Analytics (inside Security Analytics), AI bot blocking / AI Labyrinth, managed robots.txt handling, static-resource protection, WordPress optimization, and optional JavaScript Detections.
4. **You act on the score yourself.** Unlike BFM/SBFM which ship category → action mappings, Bot Management primarily exposes signals; you write WAF custom rules (or Workers) on `cf.bot_management.*` fields to block, challenge, log, or skip per path, per IP, per fingerprint.

## Bot score mechanics (1–99)

1. **Score bands.** 1 = automated (heuristic high-confidence detection); 2–29 = likely automated; 30–99 = likely human; verified bots are handled as a separate non-malicious classification. The docs' rule of thumb: scores under 30 typically indicate bots.
2. **Score 0 means "not computed", not "safe".** Requests handled entirely at the edge before Bot Management ran (for example, resolved by a Redirect Rule) get 0. Never write `cf.bot_management.score lt 30` without considering that 0 traffic will match too — decide explicitly whether `le 29` (excludes 0) or including 0 is what you want.
3. **The ML engine.** Most scores 2–99 come from a supervised model trained on billions of daily requests, taking headers, session characteristics, and browser signals and outputting a human-probability mapped to 1–99; it is periodically retrained, so score distributions can drift — re-baseline thresholds after model updates (enable ML auto-updates to get them).
4. **Heuristics and the deprecated anomaly engine.** A pattern-matching database of known-malicious fingerprints assigns score 1 (occasionally 29 during overlap assessment). Per-site behavioral anomaly detection is deprecated with no new onboarding; treat "anomaly detection" as legacy when reading old runbooks.
5. **Session smoothing via `__cf_bm`.** A Cloudflare cookie smooths scores across a user's session to cut false positives; one weird request from a real browser session does not instantly get a bot score. Clearing cookies resets this — expect occasional re-challenges, and do not build anything that assumes score stability across cookie clears.

## The cf.bot_management.* fields (rules, Workers, logs)

1. **Core fields.** `cf.bot_management.score` (Number 1–99), `cf.bot_management.verified_bot` (Boolean), `cf.bot_management.static_resource` (Boolean — static file extensions are exempt from bot detection), `cf.bot_management.js_detection.passed` (Boolean), `cf.bot_management.ja3_hash` and `cf.bot_management.ja4` (String fingerprints), `cf.bot_management.detection_ids` (Array of heuristic detection IDs), `cf.bot_management.bot_tags["<TAG>"]` (Boolean, e.g. "google"), `cf.bot_management.signed_agent` (Web Bot Auth signer), and `cf.bot_management.corporate_proxy` (Boolean).
2. **Where they can be used.** WAF custom rules (all phases), rate-limiting counting characteristics (Enterprise-only parameters), Workers via the `request.cf` object, and — since July 2026 — Cache Rules expressions, so you can serve shorter TTLs to low-score clients without blocking them.
3. **Logpush / GraphQL names differ from rule names.** The `http_requests` dataset exposes `BotScore`, `BotScoreSource`, `BotTags`, `JA4`, `JA4Signals`, and `JSDetectionPassed` (values `passed` | `failed` | `missing`); JA4/JA4Signals/JSDetectionPassed require the Bot Management subscription and some need the account team to enable them. `ip.src.asnum` needs no subscription; all bot fields do.
4. **Missing-field discipline.** Fingerprints and JS-detection fields can be absent (plain HTTP, skipped phases, Workers-routed traffic). Workers code must tolerate missing values and excluded `NaN`/`Infinity` in JA4 Signals; rules referencing them simply won't match absent values.

## JA3 and JA4 fingerprints

1. **What they are.** Fingerprints of how a client initiates TLS connections — stable across destination IPs, ports, and certificates, so a bot fleet reusing one TLS stack shares one fingerprint. JA4 improves on JA3 by sorting ClientHello extensions, which collapses the number of unique fingerprints for modern browsers.
2. **Three canonical uses.** (a) Block/challenge an attacking tool's fingerprint during an incident (`cf.bot_management.ja4 eq "t13d1516h2_8daaf6152771_b186095e22b6"` style matching); (b) Skip-rule carve-outs for legitimate traffic with a known fingerprint (your mobile app often shares one fingerprint across all devices — a free "is our app" signal); (c) analytics grouping in Bot Analytics and Logpush.
3. **Caveats.** No fingerprint over unencrypted HTTP (it is computed from the TLS handshake); may be empty when Workers route traffic (O2O) or send to third-party origins; absent when Bot Management is skipped; TLS session resumption skips recalculation. Corporate NAT/proxies make many humans share a fingerprint — check `cf.bot_management.corporate_proxy` before blocking on fingerprints alone.

## Verified bots and their categories

1. **How verification works.** A bot is verified by Web Bot Auth (a cryptographic signature, surfaced as `cf.bot_management.signed_agent`, classified "intermediary") or by IP validation (published IP lists with a stable user-agent, or reverse DNS), plus honest self-identification and non-abusive behavior (robots.txt, sane rates).
2. **Categories.** Legacy category strings include "Search Engine Crawler", "AI Crawler", "AI Assistant", "AI Search", "Monitoring & Analytics", "Advertising & Marketing", "Archiver", "Feed Fetcher", "Webhooks", "Security", "Accessibility", "Academic Research", and more. Since July 2026 a behavior taxonomy (Search, Agent, Training, Transact, Data Collection, ...) plus Direct/Intermediary operation labels layers on top; Search, Agent, and Training presets exist on all plans.
3. **Default policy.** Verified bots are allowed by default across plans, and most customers keep `cf.bot_management.verified_bot` traffic allowed. Use the AI-bot policy settings or bot-tag/category rules to selectively block (e.g., AI training) rather than globally un-allowing verified bots.

## Writing and tuning rules on scores

1. **Ship with the documented templates, not freehand thresholds.** Definite bots: `(cf.bot_management.score eq 1 and not cf.bot_management.verified_bot and not cf.bot_management.static_resource)`. Likely bots: `(cf.bot_management.score ge 2 and cf.bot_management.score le 29 and not cf.bot_management.verified_bot and not cf.bot_management.static_resource)`. Always exclude verified bots and static resources unless you have a reason not to.
2. **Per-path thresholds are the whole point of Enterprise.** Put a block on `score le 14` for `/login` and `/api/*`, a managed challenge on `le 29` for content paths, and log-only elsewhere — this is what SBFM cannot do. Scope with `http.request.uri.path` in the same expression.
3. **JavaScript Detections rule.** After enabling JSD (a toggle on this tier), challenge non-browser flows: `(not cf.bot_management.js_detection.passed and http.request.method eq "POST" and http.request.uri.path in {"/login" "/checkout"})` — JSD only injects into HTML responses, so pair it with score rules for API/mobile traffic.
4. **Ordering and monitoring.** Score-based custom rules run before SBFM/managed bot settings and can shadow them; deploy in Log action first, watch Security → Events for a week, then escalate to managed challenge, then block. Tune thresholds from Bot Analytics score distributions, not vibes. Keep a Skip rule ready for partner IPs/user agents that mis-score.

## Session and behavioral signals

1. **`__cf_bm` session smoothing.** The per-zone cookie carries bot-score session context; treat an isolated low score inside an otherwise human session as a tuning signal, not an incident. Disabling cookies in a client (curl, headless) is itself correlated with low scores.
2. **JA4Signals (behavioral statistics per fingerprint).** Inter-request statistics (ratios, ranks, quantiles) computed per JA4 fingerprint and exposed in Logpush/Workers — useful for distinguishing "one fingerprint, human pacing" from "one fingerprint, scripted pacing". Contact the account team to enable the field.
3. **`corporate_proxy` and `detection_ids`.** Corporate egress proxies make office humans look like shared-fingerprint bots — exclude `cf.bot_management.corporate_proxy` from aggressive rules. `cf.bot_management.detection_ids` lists which heuristics fired, letting you target specific detection classes (e.g., headless-browser indicators) with narrower rules than raw score.

## Related

- `bot-fight-mode-free-vs-super.md` — the Free/Pro/Business bot toggles and the SBFM boundary this article deliberately stays above.
- `paid-tier-security-upgrade-runbook.md` — where Bot Management sits in an overall paid-tier rollout (order of operations, prerequisite plan work).
- `waf-best-practices.md` and `waf-managed-rules-exception-order-and-future-rule-drift.md` — Ruleset Engine expression patterns, Skip ordering, and drift that score rules inherit.
- `waf-rate-limiting-deep-dive.md` — rate limiting counting on bot score/JA4 (Enterprise parameters).
- `api-shield-schema-validation-2-rollout.md` — the log-then-enforce rollout discipline that score rules should copy.
- `turnstile-best-practices.md` — application-layer proof-of-humanity for endpoints where scores are inconclusive.
