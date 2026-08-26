# security-level-ip-access-rules

**Issue:** An operator wants "block this attacker IP", "whitelist the office range", "challenge this ASN", or "block country X", and reaches for the legacy Security Level slider and IP Access Rules. As of 2025-2026 the Security Level feature has been fundamentally reworked — the old threat-score-driven levels are effectively retired — while IP Access Rules remain available on every plan (including Free) but carry dangerous bypass semantics for "Allow". This article maps what each control does today, what is deprecated, and where the paid boundaries are (country blocking, Zone Lockdown).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Security Level: what changed in 2025-2026

1. **The old levels are no longer the mechanism.** Historically the zone Security Level (Off / Essentially Off / Low / Medium / High) mapped to thresholds on a 0-100 Cloudflare threat score, issuing challenges to visitors whose score exceeded the level's threshold. The current docs describe the old dashboard as fixed at "Always protected" with no ability to change the setting.
2. **Security level is now the Under Attack switch.** In the new security dashboard, the Cloudflare API, and Terraform, the security level setting is used "to turn Under Attack mode on or off". The practical levels that remain meaningful are normal operation versus `under_attack`.
3. **The threat score is dead — do not build on it.** The docs state plainly: "Now, the threat score is always 0 (zero)" and "we do not recommend creating rules based on the threat score, since this score is no longer being populated". Any surviving custom rule or integration keyed on `cf.threat_score` is matching nothing and must be migrated.
4. **Per-path aggressiveness moved to configuration rules.** The old pattern of raising the security level for the whole zone is replaced by configuration rules that can apply challenge settings (including I'm Under Attack) to a filter expression such as a URI path or hostname.
5. **Terraform/API users take note.** If your IaC still patches `security_level` to `medium`/`high`, those values no longer do what the 2023-era modules implied — align your modules with the on/off reality and manage aggressiveness in rules instead.

## IP Access Rules: selectors, actions, and free-tier availability

1. **Available on every plan, including Free.** IP Access Rules allowlist, block, and challenge traffic based on the visitor's IP address, IP range, Autonomous System Number (ASN), or country. This is one of the few security controls with real free-plan reach.
2. **Generous limits.** The documented rule cap is 50,000 rules per account on Free, Pro, and Business alike (Enterprise starts at 50,000 with the option to purchase more) — you will hit maintainability problems long before the limit.
3. **Actions: block, challenge, allow.** Block drops the request; challenge issues a challenge page; allow (the "whitelist") exempts matching traffic from other security features. The challenge action follows the modern managed-challenge machinery.
4. **Country blocking is Enterprise-only in this UI.** "Block by country is only available on Enterprise plans" — for geoblocking on Free/Pro/Business, Cloudflare directs you to WAF custom rules using the Country field instead.
5. **Cloudflare recommends custom rules over IP Access Rules.** For IP-based and geography-based blocking, the current guidance is to use custom rules (IP lists in expressions for IPs, Country/Continent/AS Num fields for geography), because they are versionable, composable with other rules, and support the Skip action for precise exemption rather than the blanket Allow.

## The dangerous parts: Allow semantics and ordering

1. **Allow bypasses nearly everything.** Allowing an IP or ASN "will bypass any configured custom rules, rate limiting rules, WAF Managed Rules, and firewall rules (deprecated)". A whitelist entry created to fix one false positive silently disables your entire WAF posture for that source.
2. **Country Allow is slightly narrower.** Allowing a country bypasses custom rules, rate limiting, and legacy firewall rules — but not WAF Managed Rules. Know the difference before relying on either.
3. **Allow rules are invisible in Security Events.** Allowlisted traffic does not show up in Security Events by design, so a bad Allow rule both weakens you and hides the evidence.
4. **Globally-allowed Cloudflare IPs outrank country blocks.** IP addresses globally allowed by Cloudflare override an IP Access Rule country block (but not a country block via custom rules) — an edge case that matters when testing geoblocking.
5. **Fail2ban behind Cloudflare cuts both ways.** If you run fail2ban at origin, restore original visitor IPs (e.g. via `CF-Connecting-IP`) before banning, or you will ban Cloudflare edge IPs and take yourself offline.
6. **Precedence is coarse.** IP Access Rules are not Ruleset Engine phases — they are evaluated outside the ordered custom-rule pipeline, which is another reason the docs steer new work toward custom rules.

## Zone Lockdown and other paid boundaries

1. **Zone Lockdown is paid-plan only.** Zone Lockdown (allow *only* specified IPs/ranges to reach specified URLs, blocking everyone else) "is available on paid plans" — it is not on Free. Free-tier zones approximate it with a custom rule that blocks all traffic to a path except listed `ip.src` values.
2. **Lockdown vs Allow.** Zone Lockdown is the inverse of whitelisting: default-deny per path. It is the right primitive for admin panels and internal dashboards on Pro+, whereas IP Access Rule Allow is default-allow and much riskier.
3. **Custom rules with the Skip action are the modern exemption.** Where legacy guidance said "whitelist the scanner IP", the current pattern is a custom rule matching the trusted source with a Skip action scoped to specific features — the exemption is then visible, ordered, and reviewable.
4. **Free-tier coverage summary.** Free gets: IP/range/ASN block+challenge and country challenge in IP Access Rules, full custom rules, and the managed DDoS baseline. Free does not get: country block via IP Access Rules (Enterprise), Zone Lockdown (paid), or IP Access Rules with purchased quotas beyond 50k (Enterprise).

## Related

- `free-tier-domain-security-runbook.md` — overall free-plan posture and how these controls compose.
- `under-attack-mode-ddos-runbook.md` — the security level setting now doubles as the Under Attack switch; that article covers the emergency flow.
- `waf-best-practices.md` — custom rules as the replacement primitive for most IP Access Rule use cases.
- `api-token-least-privilege-and-rotation-governance.md` — govern who can create Allow rules; they are security-critical, not housekeeping.
