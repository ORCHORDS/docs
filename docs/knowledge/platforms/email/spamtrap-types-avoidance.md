# spamtrap-types-avoidance

**Issue:** A sender's domain reputation collapses after one campaign: they land on a blocklist (Spamhaus SBL/ESP-specific) or get junk-foldered everywhere, and diagnosis shows they hit spamtraps — addresses operated by ISPs and blocklist operators purely to catch illegitimate senders. Traps send no bounces, generate no opens, and issue no complaints; they are invisible except through their damage. Because different trap types indicate different root causes (list acquisition fraud vs. stale hygiene), the sender needs to identify which type they hit and remediate the corresponding pipeline failure, not just wait out the blocklist.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Trap taxonomy

1. **Pristine traps.** Addresses that have never belonged to a real person — planted on websites (hidden in HTML, styled invisibly, or placed in honeypot signup forms), forum posts, and published lists specifically to be harvested by scrapers and sold to list buyers. Hitting one proves scraping or purchased-list usage and typically triggers immediate blocklisting (Spamhaus SBL/PBL escalation) — the most severe single-hit consequence.
2. **Recycled traps.** Addresses that were once real (closed accounts, abandoned mailboxes, role addresses like `info@`/`sales@` repurposed by the provider) that now accept mail silently while feeding reputation systems. Hitting these signals poor list hygiene — usually you kept mailing long-dead subscribers — and causes progressive junk-foldering rather than instant blocking.
3. **Typo traps.** Domain typos of real providers (`gmial.com`, `hotmial.com`) where the typo domain's catch-all collects mis-typed signups. These indicate you accepted an unverified email at signup without confirmation or syntax/typo checks.
4. **Honeypot forms / spam-trap domains.** Entire domains or hidden form fields operated by trap networks; any address @those domains or submitted through the hidden field is a trap by construction. Co-registration vendors and scraped "opt-in" feeds are heavily seeded with these.
5. **Re-engagement traps.** A subset of recycled: blocklist operators monitor addresses inactive for years, so mailing a "we miss you, confirm you still want email" to a 5-year-dormant segment is the classic way otherwise-legitimate senders hit traps during win-back campaigns.

## How traps get onto your list

1. **Purchased or rented lists.** The dominant source of pristine traps — no matter what the vendor claims about "double opt-in," harvested and seeded addresses are in every commercial list.
2. **Signup form abuse and bots.** Public forms without CAPTCHA/rate limiting get bot-filled with trap addresses (deliberately submitted to catch later mailers); a signup spike of gibberish addresses at 3am is the fingerprint.
3. **No verification at entry.** Accepting a signup without email confirmation (double opt-in) or real-time validation lets typo traps and dead-role recycled traps in at zero cost.
4. **Stale subscribers never sunset.** Keeping addresses that have not engaged in 12+ months converts formerly-good addresses into recycled-trap hits when the provider repurposes the mailbox.
5. **List transfers/imports.** Importing "legacy" CRM contacts or merged-database users who never opted into this sender imports their traps with them.
6. **Shared/co-registration lead gen.** Checkbox-pre-checked partner offers route recipients to lists they never meaningfully chose, seeded with traps by the operators who police such flows.

## Detection signals (you can't see traps directly)

1. **Zero-engagement segments.** Traps never open, never click, never move the needle; a large "delivered but silent forever" cohort is where traps statistically live — segment it and treat it as high-risk.
2. **Blocklist listings naming the issue.** Spamhaus listings distinguish causes: SBL (spam operation / pristine hits), CSS (volume + trap hits from snowshoe sending), PBL (policy). The listing text often states the trap campaign dates — map those to specific sends.
3. **Spamhaus Domain Reputation System / Google Postmaster spam-rate anomalies.** A domain-reputation drop with a near-zero complaint rate is a classic trap-hit signature (traps don't complain, they only damage reputation).
4. **Seed-list forensics.** Inbox-placement tools (Google Postmaster v2, Microsoft SNDS data, return-path style panels) showing sudden junk placement without complaint spikes points at trap or infrastructure causes rather than content.
5. **Delivered-but-no-MX-history addresses.** Pre-send, addresses at domains with catch-all MX configurations that accept everything should be flagged; combined with zero engagement history they are the highest-probability trap population.

## Prevention practices

1. **Double opt-in (confirmed subscription) on every acquisition surface.** The single most effective control: a confirmation email to the claimed address means pristine and typo traps (which never receive or never confirm) never enter the list.
2. **Never buy, rent, or co-register lists.** No remediation makes purchased data safe; blocklist operators treat any mailing to harvested addresses as spam regardless of vendor documentation.
3. **Protect forms.** CAPTCHA/behavioral bot detection, hidden-field honeypots of your own (fill = reject), rate limits per IP, and immediate rejection of known trap domains stop bot-seeded entries.
4. **Sunset policy with escalation, not cliff.** After 6 months of no engagement, reduce frequency; after 12, move to re-permission confirmation; after 18, suppress. Never bulk-mail a multi-year dormant segment — that is the re-engagement trap scenario.
5. **Real-time validation at signup.** Syntax checks, MX lookup, disposable/role-address flagging, and typo-domain suggestions ("did you mean gmail.com?") catch typo and dead-role traps pre-confirmation.
6. **Re-permission, don't resurrect.** For legacy/dormant imports, mail once asking for explicit confirmation to continue; non-confirmers are suppressed permanently. Traps in the segment never confirm and exit automatically.

## Remediation after a hit

1. **Stop sending to the suspect segment immediately.** Every additional trap hit compounds the listing; pause campaigns to the unengaged cohort while investigating which send dates the listing references.
2. **Identify the type from the listing cause.** Purchased-list or scrape indication → pristine: purge the acquisition source entirely and audit who else mailed it. Hygiene indication → recycled: run aggressive sunset/suppression on inactives.
3. **Request delisting only after the cause is fixed.** Spamhaus and most blocklists require a genuine remediation narrative (what failed, what changed); delisting requests without list cleanup get denied and repeated requests worsen standing.
4. **Quarantine, don't delete-and-continue.** Keep suppressed trap-suspect addresses in a permanent do-not-mail list so future imports cannot re-add them; deleting them invites re-hitting on the next campaign.
5. **Verify warm-up discipline for new infrastructure.** Post-remediation, re-warm IPs/domains gradually while monitoring Spamhaus and Postmaster spam rate; a trap hit during warming re-escalates faster than from an established sender.
