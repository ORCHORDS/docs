# under-attack-mode-ddos-runbook

**Issue:** A zone is actively absorbing a layer 7 flood (credential stuffing, request floods, scrapers) and the on-call engineer is deciding whether to flip "I'm Under Attack Mode" (UAM). The mode is a blunt instrument: it inserts a challenge interstitial in front of every visitor, which hard-breaks every non-browser client — API consumers, mobile app backends, uptime monitors, webhook receivers — exactly when the business is already hurting. This runbook covers what UAM does in 2025-2026, the free-tier DDoS baseline it sits on top of, how to scope it so APIs survive, and how to exit it cleanly.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What I'm Under Attack Mode actually does

1. **An interstitial challenge in front of the whole zone.** UAM presents the "Checking your browser before accessing..." page, which runs browser checks and "decides within five seconds" whether to admit the visitor. In the current docs, enabling UAM causes Cloudflare to "present a Managed Challenge page" — the legacy "JavaScript challenge" framing has been superseded by the managed challenge machinery.
2. **Last resort by design.** It "is designed to be used as one of the last resorts when a zone is under attack". It is a circuit breaker, not a steady-state posture.
3. **Requires a JavaScript-capable browser.** Since browsers must support JavaScript to pass, non-browser HTTP clients (curl, SDKs, webhooks, RSS readers, uptime probes) cannot pass and will fail outright — Cloudflare explicitly warns the mode "may affect some actions on your domain, such as your API traffic".
4. **Analytics side effects are expected.** Cloudflare documents that third-party analytics tools will be impacted and site analytics will be skewed, because the challenge page intercepts requests before your origin (and your own tags) ever see them.
5. **Challenge passage gives humans a break.** A visitor who passes is not challenged again until the configured Challenge Passage duration expires — so legitimate humans see the interstitial roughly once per passage window, not per request.

## The free-tier DDoS baseline (this is what you get without touching anything)

1. **Unmetered L3-L7 on every plan, Free included.** The availability table marks "Standard, unmetered DDoS protection (layers 3-7)" as available on Free, Pro, Business, and Enterprise. Volumetric attacks Cloudflare absorbs at the edge do not traverse your origin or its bandwidth.
2. **Detection is autonomous.** Cloudflare's autonomous DDoS systems detect and mitigate attacks automatically via dynamic rules exposed as managed rulesets — you do not have to enable anything for the baseline to function.
3. **Both rulesets are customizable on all plans.** Network-layer (L3/4) DDoS rules and HTTP (L7) DDoS rules can be adjusted even on Free, with a single ruleset override (Enterprise with the Advanced DDoS Protection add-on gets expression fields and up to ten overrides).
4. **UAM is the manual escalation on top.** The managed DDoS systems handle floods; UAM exists for the attacks the autonomous systems do not fully cut off (e.g., low-and-slow or distributed abusive-but-valid-looking requests).
5. **Paid tiers add sensitivity, not the protection itself.** Adaptive DDoS Protection and Advanced TCP/DNS protections are paid/Magic Transit features — the unmetered mitigation core is not the upsell.

## When to flip it on, and how to keep APIs alive while it is on

1. **Trigger conditions.** Flip UAM when origin load or request rate is anomalous *and* lower-cost controls (rate limiting rules, custom rules blocking the pattern, managed DDoS ruleset sensitivity) have not cut the traffic — or when the attack signature is so distributed that per-IP controls are hopeless.
2. **Enable it from the zone overview.** Dashboard: zone overview > Quick Actions > toggle Under Attack Mode. Via API/Terraform: the zone's security level setting with `under_attack` (in the new dashboard the security level setting *is* the UAM on/off switch — see security-level-ip-access-rules.md).
3. **Scope it instead of going zone-wide when possible.** A configuration rule can apply "I'm Under Attack" only to matching paths — e.g. `starts_with(http.request.uri.path, "/admin")` — leaving API routes untouched. This is the single most important lever for mobile-app-backed zones.
4. **Exempt trusted automation explicitly.** IP Access Rules can challenge or allow specific ASNs, countries, or IP ranges, so payment webhooks and partner integrations can be carved out. Caution: an Allow in IP Access Rules bypasses custom rules, rate limiting, and managed rules — allow only what you truly trust.
5. **Tell your users it is coming.** The interstitial is visible. If the attack is public-facing, a status-page note prevents a support spike on top of the incident.

## Exit criteria and post-incident checks

1. **Time-box the mode.** UAM should ride only for the duration of the attack. Monitor zone analytics (Security Events, traffic graphs) and step back down to normal as soon as request rates and origin load normalize.
2. **Disable the same way you enabled it.** Untoggle in Quick Actions or set the security level back to its prior value; if you created scoping configuration rules or IP Access Rules exceptions during the incident, review and delete the temporary ones deliberately — forgotten Allow rules are a standing security hole.
3. **Check what the challenge hid.** Challenge-served traffic does not reach your origin: verify logs, caches, and analytics baselines recover, and re-check that nothing was cached with challenge responses while it was on.
4. **Harden so the next flip is unnecessary.** Post-incident, move the durable defenses into rate limiting rules, custom rules for the attack signature, and WAF managed rules; if the abuse is form/account oriented, add Turnstile at the application layer instead of relying on zone-wide UAM.
5. **Loopback services need attention too.** Note that WordPress loopback diagnostics and similar self-calling tooling can be blocked by UAM (Cloudflare calls this out for Super Bot Fight Mode, and the same logic applies to the UAM challenge) — expect false "site health" failures while the mode is active.

## Related

- `free-tier-domain-security-runbook.md` — where UAM sits in the overall free-plan defense stack (DDoS baseline > WAF > bots > UAM as the break-glass tier).
- `security-level-ip-access-rules.md` — the security level setting is now the UAM switch; IP Access Rules are the exemption mechanism.
- `waf-rate-limiting-deep-dive.md` — the durable control that should replace most UAM flips.
- `bot-fight-mode-free-vs-super.md` — bot-driven floods vs DDoS floods: which switch to pull for which.
