# mx-migration-cutover-planning

**Issue:** Moving a domain's inbound mail from one mail provider to another (on-prem Exchange to Google Workspace, legacy host to Microsoft 365, or between filtering services) risks silently losing messages during the DNS transition. Senders cache MX records for the TTL, remote MTAs retry on 4xx for hours or days, and messages already queued at the old provider must be drained before it is decommissioned. A botched cutover produces no bounce, no error, and no trace — just mail that vanishes. Unlike web migrations, email failures are asynchronous and often noticed days later, so the plan must control TTLs, run both systems in parallel, sequence dependent records (SPF/DKIM/DMARC, autodiscover), and keep a tested rollback path. This article is the cutover playbook; basic MX record syntax is covered in mx-record-configuration.md.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Pre-cutover groundwork

1. **Lower the MX TTL 24 to 48 hours ahead.** Drop the TTL on the MX records (and any dependent A/AAAA records for mail hostnames) to 300-600 seconds at least a full day before the switch. The current long TTL must fully expire before the new short value is what resolvers hold; lowering the TTL on the day of the cutover accomplishes nothing.
2. **Inventory every dependent record before touching MX.** SPF includes, DKIM selectors and keys, DMARC policy, autodiscover/autoconfig endpoints, MXBackup/secondary MX targets, SRV records, and TLSA/MTA-STS records all interact with the mail path. MTA-STS policy files reference specific MX hostnames and must be updated in tandem or sessions will fail validation after cutover.
3. **Pre-provision the destination.** Create all mailboxes, aliases, distribution lists, and forwarding rules on the new provider and verify authentication (SPF for the new sending setup, DKIM keys published, DMARC still aligned) before any traffic flows. Run a test message through the new stack end to end using a staging domain if possible.
4. **Baseline current mail flow.** Capture normal daily volume, peak hours, external sender patterns, and queue depths so you can distinguish "migration hiccup" from "normal Tuesday" during validation.

## Cutover sequencing

1. **Switch MX priorities to coexist, not replace.** The safest pattern is adding the new provider's MX at a higher priority (lower preference number) while leaving the old MX in place at a lower priority. Senders that pick up the change go straight to the new system; resolvers holding the old record still deliver somewhere valid.
2. **Cut during the lowest-traffic window.** Even with short TTLs, a slice of traffic follows cached records. Choose the weekend or overnight valley for the domain's audience so the overlap period handles minimal volume.
3. **Never drop SPF or DMARC records during the window.** Removing or misordering TXT changes while MX propagates creates intervals where mail from the domain fails authentication on forwarding or re-emission paths. Publish additive SPF includes first, flip MX, then prune old values only after the old provider sees zero traffic.
4. **Freeze unrelated DNS and app changes.** One variable at a time: no template deploys, ESP changes, or other migrations during the cutover week, or debugging becomes guesswork.

## Dual-run and queue draining

1. **Keep the old provider receiving for at least 7-14 days.** Cached records, slow-updating resolvers, and senders with long-running queues will hit the old MX well past your TTL window. The old system should accept mail and either forward it to the new system or hold it for manual drain — rejecting during this period loses messages.
2. **Forward, do not hold, wherever possible.** Configure the legacy host to relay inbound mail to the new provider's inbound gateway (contact addresses or journaling rules). This gives near-zero-touch continuous drain and a single place to watch for looping.
3. **Drain and export the old queues before decommission.** Pull any undelivered queue entries, export mailboxes and archives (PST/IMAP sync/migration tooling), and reconcile counts against the baseline. Only then schedule the old provider for deletion — after a final backup.
4. **Watch loop risk in the forwarding bridge.** If both systems are configured to relay to each other, a misaddressed recipient creates a bounce loop. Tag forwarded traffic and set a hop-count tripwire.

## Validation and rollback

1. **Probe from independent vantage points.** After the MX flip, verify resolution from multiple public resolvers (and dig against authoritative servers directly) and send test mail from at least three external providers (Gmail, Outlook.com, a non-big-provider domain) confirming arrival, header path, and spam-folder placement on the new system.
2. **Monitor the old provider's logs to zero.** The formal end-state for cutover is N consecutive days of zero inbound messages at the legacy host. Log queries are the source of truth, not TTL arithmetic.
3. **Keep a rehearsed rollback.** Because the old MX stays published at lower priority during dual-run, rollback is raising its priority back — a single DNS edit taking effect in minutes thanks to the pre-lowered TTL. Document the exact record values and the decision criteria (who declares, within how many hours) before the window starts.
4. **Verify client access cutover.** Mail clients cache server settings aggressively; confirm autodiscover/autoconfig records point at the new provider and expect a tail of users on old settings for days. Communicate the exact date passwords/settings change.

## Post-cutover cleanup

1. **Restore sane TTLs.** Raise MX TTLs back to 3600-14400 seconds once stable, so resolver load normalizes and accidental edits do not propagate instantly.
2. **Prune the old provider's DNS footprint deliberately.** Remove old SPF includes, DKIM selectors, and MX backup targets only after the old system is fully drained and export-verified, in separate change windows, with DMARC reports watched for new failures after each removal.
3. **Update MTA-STS and DANE publications.** Publish the new MX set in the MTA-STS policy (mind the staging-vs-production policy id increment) and rotate TLSA records if DANE is in use, then confirm TLS-RPT reports show the new hosts negotiating TLS cleanly.
4. **Run the audit at plus-30 days.** A month out, sweep DMARC aggregate reports, MTA-STS/TLS-RPT data, and bounce logs for any sender still authenticating or delivering via the old path; stragglers usually indicate a forgotten secondary MX or application hardcoded to the legacy hostname.
