# sanctions-screening-list-management

**Issue:** Any platform that moves money, pays out sellers, or sells into the EU/US must screen customers, sellers, beneficiaries, and counterparties against government sanctions lists — OFAC's SDN and consolidated lists, EU consolidated lists, and UK OFSI regimes — before funds are committed, and continuously afterward as lists change weekly. The engineering problem is threefold: name matching is fuzzy (transliteration, aliases, dirty data), list scope is broader than the published names because OFAC's 50 Percent Rule blocks entities that never appear on any list, and a hit mid-transaction creates a legal obligation to freeze ("block") assets and file reports rather than simply decline. In 2025 OFAC updated its ownership/control FAQs to emphasize that control by blocked persons — not just 50 percent aggregate ownership — creates enforcement risk for counterparties, which means screening systems can no longer rely on name-list equality alone. Violations carry strict civil liability (no intent required) with penalties per violation that adjust annually for inflation.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Lists and data ingestion

1. **Enumerate the regimes you must screen.** At minimum US (SDN plus the Consolidated Non-SDN list including sectoral sanctions and the CAPTA list), EU consolidated list, and UK OFSI consolidated list if you touch UK persons or USD clearing; add UN lists if you operate platforms with global payout rails. Each regime has different legal effect — a UK-sanctioned entity may not be US-sanctioned and vice versa, so record which regime produced the hit on every alert.
2. **Automate list ingestion with change detection.** Pull the machine-readable formats (OFAC's SDN and consolidated files, EU's data feed, OFSI's CSV) on a schedule, parse program codes and aliases, and store full list snapshots with effective dates — an enforcement defense requires proving what the list looked like on the transaction date. Alert on ingest failures; a stale list is a silent compliance failure.
3. **Model the 50 Percent Rule as data, not just matching.** Because entities owned 50 percent or more in the aggregate by blocked persons are themselves blocked without being listed, ingest corporate-registry and beneficial-ownership data (e.g., 30+ percent ownership signals from registries) to flag implicitly blocked entities. OFAC's 2025 guidance push toward control-based analysis means your graph should also capture director overlaps and control relationships as secondary risk signals.
4. **Handle delisting and list changes forward and backward.** Delisted parties must be unblocked and screening suppressions updated the same day; test that suppression entries carry expiry dates rather than persisting forever.

## Matching engine design

1. **Use fuzzy matching tuned for names.** Exact-match screening is indefensible; standard practice combines transliteration normalization (Cyrillic, Arabic, Chinese pinyin variants), diacritic folding, token reordering, and matching algorithms such as Jaro-Winkler or Jaccard with list-specific thresholds. Publish your threshold rationale — regulators ask why a 0.85 cutoff was chosen.
2. **Screen more than the display name.** Fuzzy-match against aliases (AKAs), weak aliases, and — for payouts — the bank account number and BIC/IBAN against list-linked financial identifiers; many OFAC entries carry exact passport and account identifiers that give deterministic hits on otherwise-impossible names.
3. **Tier your screening by risk.** Real-time hard-block on high-confidence matches at payment time, queue medium-confidence matches for human review within a defined SLA (typically 24-48 hours), and batch re-screen the entire user base whenever lists update — a customer cleared last month may be designated today.
4. **Log the decision, not just the hit.** Every alert needs an immutable record of who reviewed it, what data they consulted, and why it was dismissed or escalated; "cleared by analyst, similar name, different DOB" without evidence is a recurring finding in OFAC enforcement settlements.

## Blocking, rejecting, and reporting workflows

1. **Distinguish block from reject.** US-origin funds or property of a blocked person must be frozen in place (moved to a blocked interest-bearing account, no further dealings) — rejecting/returning a blocked-party payment is itself a violation; build both flows and train the payment engine to choose correctly by regime. EU and UK rules lean toward freezing with reporting to the national competent authority.
2. **Automate the reporting clock.** OFAC blocked-property reports (within 10 business days, annual renewals), and OFSI/EU reports to national authorities, should be calendar-driven from the moment of the block, with the underlying transaction evidence snapshotted at freeze time.
3. **Build the true-up and offset path.** If a false positive was blocked, unblocking requires documented evidence and, in some regimes, regulator notification; the funds movement needs the same audit trail as the original freeze.

## Program guardrails

1. **Write a sanctions compliance commitment into onboarding.** Terms of service should prohibit sanctioned persons, require beneficial-ownership declarations above a threshold, and contractually permit immediate account freeze on a hit — the contractual hook matters when you later need to withhold payouts.
2. **Geo and currency signals are screening inputs.** IP geolocation, phone country codes, billing addresses, and payout currency against comprehensively sanctioned jurisdictions (e.g., Iran, North Korea, Syria, Cuba, and the Russia/Crimea regions under US, EU, and UK law) should trigger enhanced review even without a name hit; comprehensive embargoes are territory-based, not list-based.
3. **Test with known-bad corpora.** Seed staging with synthetic users matching real SDN entries (transliterated, aliased, partial) and run quarterly recall tests; OFAC settlements routinely cite "deficient screening" that internal testing would have caught.
4. **Keep voluntary self-disclosure criteria handy.** If a violation is discovered, OFAC treats voluntary self-disclosure as a major mitigating factor with sharply reduced penalties — the decision path and escalation owner should be documented before you need them.
