# p2b-ranking-transparency-platform-terms

**Issue:** Regulation (EU) 2019/1150 — the Platform-to-Business (P2B) Regulation — imposes fairness and transparency duties on online intermediation services (marketplaces, app stores, comparison tools, social platforms used by business users for promotion) and online search engines toward their business users. It is the regulation no platform team has heard of yet regulators actively enforce: French and Italian authorities have already pursued ranking-transparency failures, and business users can claim damages directly. Core engineering duties include disclosing the main parameters and relative importance of ranking (Art. 5), publishing terms and conditions in plain language with at least 15 days' advance notice of changes, and operating complaint-handling — duties that complement DSA recommender transparency (see `dsa-online-platform-obligations-2026.md`) without overlapping its content-moderation scope.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Scope and enforcement

1. **B2B by design.** P2B protects business users and corporate website users in their relations with providers of online intermediation services and online search engines — consumers are covered by consumer law, not here, which is why platform teams overlook it.
2. **Wide definition of intermediation.** Any service that allows business users to promote offers or reach consumers (including social platforms where businesses post or advertise, app stores, and comparison sites) is in scope regardless of size; there is no small-provider exemption.
3. **Directly enforceable by business users.** Terms that breach P2B cannot be enforced against the business user, and businesses can sue for damages — the regulation is not just regulator-enforced (CCPC [P2B overview](https://www.ccpc.ie/enforcement-and-regulation/digital/platform-to-business-regulation)).
4. **National enforcement with teeth.** Member-state authorities (e.g., DGCCRF in France, AGCM in Italy) enforce with national penalties, and French and Italian proceedings against major platforms show ranking-transparency failures are actionable in practice ([BDK Advokati](https://bdkadvokati.com/p2b-regulation-has-teeth-french-and-italian-regulators-show)).
5. **Forerunner to DSA/DMA.** P2B's ranking duties are referenced by the DMA and echo in DSA Art. 27; one well-designed ranking-disclosure artifact can serve all three regimes ([Arthur Cox analysis](https://www.arthurcox.com/knowledge/platform-to-business-regulation-an-overlooked-forerunner-to-the-digital-services-package/)).

## Ranking transparency (Art. 5)

1. **Main parameters and their relative importance.** The platform must describe in its terms and conditions the main parameters determining ranking and the relative importance of those parameters, in plain and intelligible language (Commission [ranking guidelines, CELEX 52023DC0525](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:52023DC0525)).
2. **Payments must be disclosed.** Any direct or indirect influence of payments (advertising, promoted placement, commission rates) on ranking must be flagged as part of the main-parameter disclosure — including where higher commissions quietly improve placement.
3. **Describe major changes.** Significant changes to ranking parameters must be described in advance, which turns the ranking model's release notes into a legal disclosure document.
4. **Search engines too.** Art. 5(2) imposes the equivalent duty on providers of online search engines, covering general search results pages as well as specific search queries.
5. **Trade-secret balance, not an excuse.** Art. 5(6) protects trade secrets, but the balance (analysed in the 2025 literature, [Springer](https://link.springer.com/article/10.1007/s40319-025-01625-1)) requires disclosing what drives prominence at a parameter level — "it's proprietary" is not a compliant answer, while categories and relative weights are.

## Contract and terms duties

1. **Plain-language terms.** Terms and conditions must set out the essential information on ranking, main parameters for access, and contractual changes in clear, unambiguous language; ambiguity is interpreted in the business user's favour.
2. **Advance notice of changes.** Business users must get at least 15 days' notice before changes to terms take effect, giving them a genuine opportunity to end the relationship first — mechanism, not just a policy.
3. **Restrictions on retroactive changes.** Retroactive changes are only permissible in specified circumstances with notice and justification, so the T&C system needs dated versions with effective dates and reasons attached.
4. **Complaints and mediation (Arts. 10–12).** The platform must have an internal complaint-handling process that responds within a reasonable period, inform business users of out-of-court options, and accept mediation with registered bodies — the intake, SLA clock, and outcome record all need to exist as systems.
5. **Data access and discrimination duties.** Platforms must disclose what data they collect through the service and share with third parties, and cannot use business users' data to compete against them without disclosure — align the disclosure with the data inventory kept for `gdpr-article-30-ropa-automation.md`.

## Engineering it

1. **Ranking parameter registry.** Maintain a structured registry of ranking signals, weights (at least as ordered categories), payment influences, and effective dates, versioned in git alongside the ranking model so disclosure and code cannot drift apart.
2. **Generated disclosure page.** Render the public/business-facing ranking description from the registry on every model release, with the change description (Art. 5(4)) generated as a diff report reviewed by legal before publication.
3. **T&C versioning with notice automation.** Publish each T&C version with an effective date at least 15 days ahead, notify business users through the platform, and archive prior versions with diffs — the notice history is the compliance evidence.
4. **Complaint pipeline with SLAs.** Implement complaint intake for business users with status tracking, response-time SLAs, and escalation to mediation partners; export volumes and outcomes for regulator requests.
5. **Evidence exports for regulators.** Pre-build exports mapping each disclosure statement to the registry version, model release, and user-notification event, so an enforcement question is answered with artifacts instead of archaeology.

## Gotchas

1. **"Main parameters" is not the algorithm.** The duty is parameter-level disclosure with relative importance, not source code — over-disclosure risks trade-secret loss while under-disclosure risks enforcement; the Commission guidelines are the calibration point.
2. **Relative importance is required.** Listing parameters without indicating which dominate (even as high/medium/low) fails the disclosure standard per the guidelines.
3. **Paid placement must be separately identifiable.** Advertising or promoted results must be distinguishable from organic ranking, and the payment's influence must be disclosed as a ranking parameter — this is where French/Italian enforcement started.
4. **Business-user definition is broad.** Any user offering goods or services (even an individual creator monetising reach) can qualify; scope the disclosure by role, not by verified-business flag.
5. **Keep P2B and DSA disclosures in sync.** DSA Art. 27 recommender transparency and P2B Art. 5 ranking transparency cover overlapping surfaces for different audiences — generate both from the same registry so they never contradict each other in an audit.
