# dmarc-enforcement-staged-rollout

**Issue:** A team publishes a DMARC record but does not know how to move from monitoring (`p=none`) to actual enforcement (`p=quarantine`, then `p=reject`) without breaking legitimate mail. Flipping straight to `p=reject` silences every misaligned source — including forwarders, mailing lists, CRM tools, and scan-to-email appliances that send from your domain — while staying at `p=none` forever means spoofers keep landing in inboxes and Google/Yahoo bulk-sender requirements remain unmet. The missing piece is a monitoring-driven progression: using aggregate (rua) reports as the gate criteria before each policy step, with known breakage patterns handled in advance and a rollback path.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Staged progression overview

1. **Stage 0 — publish `p=none; pct=100` with rua.** The record `v=DMARC1; p=none; rua=mailto:dmarc-agg@yourdomain.com` collects daily aggregate XML from every receiver without affecting delivery; run this stage 2–6 weeks, not days, so weekly sending cycles (newsletters, payroll runs, monthly reports) all appear in the data.
2. **Stage 1 — inventory every legitimate source.** Parse rua reports to list every sending IP, SPF domain, and DKIM `d=` seen passing or failing for your domain; the classic surprise is a source nobody documented (a SaaS tool, an old marketing ESP, a printer) that will fail once enforcement starts.
3. **Stage 2 — `p=quarantine` with a `pct` ramp.** Move to quarantine in steps (e.g. `pct=10` → 25 → 50 → 100), holding each step for at least one full reporting cycle; `pct` is the receiver-side throttle on how many failing messages the policy applies to, and receivers apply it randomly, so do not treat the numbers as exact.
4. **Stage 3 — `p=reject; pct=100`.** Full enforcement only after several weeks of stable 100% quarantine with no legitimate traffic disappearing from reports and no user complaints about missing mail.
5. **Do not skip quarantine for established domains.** Straight `none → reject` is acceptable only for a brand-new domain that has never sent mail (parked domains can start at `p=reject` immediately since no legitimate source exists to break).

## Gate criteria before each policy step

1. **Alignment rate above ~98–99% for legitimate streams.** Before each tightening step, compute what share of *legitimate* message volume passes DMARC (SPF or DKIM aligned with the visible From: domain); the industry rule of thumb is not to advance while more than 1–2% of legitimate mail fails alignment.
2. **Every legitimate source identified and fixed.** Each rua-discovered sender must be either brought into alignment (correct SPF include, DKIM signing by the ESP with your `d=`) or intentionally re-homed to its own subdomain, before the gate opens.
3. **Quarantine impact verified in reports.** While in quarantine, watch rua `disposition` fields: if messages you expected delivered show `disposition=spambox`, you have misclassified a legitimate source — fix it before reject, because reject turns spam-folder into disappearance.
4. **Zero unresolved "unknown" high-volume sources.** Any unidentified source sending more than a handful of messages per day must be chased down; unexplained volume under `p=none` becomes an outage under `p=reject`.
5. **Change-management window.** Schedule policy steps outside peak sending periods and announce them internally, so a delivery failure is recognized as DMARC-related within hours instead of days.

## Common breakage: forwarders and mailing lists

1. **Forwarders break SPF by construction.** A forwarder re-sends your message with your From: domain but its own IP, so SPF fails; the fix is on the forwarder side — SRS (Sender Rewriting Scheme) for bounce correctness, plus leaving the message body and DKIM signature untouched so DKIM still passes and DMARC succeeds on DKIM alignment alone.
2. **Mailing lists break DKIM by content mutation.** List software prepends `[list-name]` to the subject, appends footer text, and re-wraps the MIME structure — any of these invalidates the DKIM body hash while the From: stays yours, so DMARC fails. Lists that rewrite the From: header ("From-munging") to their own domain sidestep DMARC entirely but change what recipients see.
3. **ARC is the mitigation receivers actually honor.** RFC 8617 (ARC) lets a trusted intermediary seal the original authentication results; Gmail and other large receivers use ARC seals from known forwarders (notably Google Groups and major list providers) to keep legitimately forwarded mail out of the bin — you cannot publish your way around a forwarder that neither preserves DKIM nor seals ARC.
4. **Internal appliances are the silent killer.** Multifunction printers, ERP systems, monitoring tools, and CRM auto-mailers often send unauthenticated mail from your exact domain with no SPF entry and no DKIM; these never show up until a rua report reveals them, and they are the most common cause of "reject broke our invoices."
5. **Verify breakage before blaming the policy.** When mail vanishes after a step-up, confirm via the rua report whether the receiving domain applied the failing disposition, versus the message never having been sent — the aggregate report is the source of truth, not anecdotes.

## Subdomains, pct, and rollback

1. **Use `sp=` to isolate subdomains.** `sp=quarantine` (or `sp=reject`) sets policy for subdomains separately from the apex policy; a common pattern is a strict apex policy plus `sp=none` while ESP subdomains (e.g. `mail.example.com`) are still being aligned, so one lagging stream cannot block apex enforcement.
2. **Nested subdomains ignore `sp=`.** The `sp=` tag applies only to direct subdomains; deeper levels fall back to the closest explicit `_dmarc` record, which is why per-stream subdomains each get their own record during rollout.
3. **`pct` is not a precise dial.** Receivers apply `pct` non-deterministically (and a few treat it conservatively), so `pct=25` is a fog, not a knife-edge 25.0%; use it as a confidence ramp, never as a guarantee that exactly 75% of failing mail still delivers.
4. **Keep a tested rollback path.** DNS TXT edits at `_dmarc` propagate on TTL timescales (typically minutes to an hour); document the exact previous record string for each stage so the on-call revert is a copy-paste, and remember lowering `p` is always safer than raising it under pressure.
5. **Watch third-party senders of your domain.** Rua reports also expose pure spoofing volume; a reject policy is working when spoofed volume shows `disposition=reject` in reports — that is the metric that justifies the whole exercise to management.

## Reporting operations during rollout

1. **Route rua to a parser, not a human inbox.** Aggregate reports arrive as gzip XML attachments from dozens of receivers daily; tools like parsedmarc, or the built-in analyzers from Postmark/Google/Valimail/dmarcian, turn them into per-source alignment tables — manual review does not scale past the first week.
2. **Expect report latency and asymmetry.** Receivers send rua once per UTC day, some skip days entirely, and coverage differs per provider; gate decisions on trends across at least 3–4 report cycles, never a single day.
3. **Ruf (forensic) reports are optional and privacy-sensitive.** Few major receivers send them at all in 2026, and they can contain full message content; enable them only to a tightly access-controlled mailbox, if at all.
4. **Track the metric that matters per stage.** Under `p=none` track *identification completeness* (unknown sources → zero); under quarantine track *disposition of legitimate streams*; under reject track *spoofed volume rejected* — each stage has a different success signal.
5. **Fold in the bulk-sender rules.** Google and Yahoo require enforced DMARC (`p=quarantine` or `p=reject`) for bulk senders, so finishing this rollout is not optional hygiene but a deliverability prerequisite for any domain sending 5,000+ messages per day to those providers.
