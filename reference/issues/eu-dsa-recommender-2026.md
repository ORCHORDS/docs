# eu-dsa-recommender-2026

**Issue:** A team builds a SaaS product with a content feed, search results, and a product recommendation system. The product is used in the EU. The team has no idea the EU Digital Services Act (DSA) requires them to disclose how their recommender system works.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU Digital Services Act (DSA) has been fully enforceable for all intermediary services since **February 2024**. Article 27 (plus Articles 38-40 for Very Large Online Platforms) creates legally binding recommender system disclosure obligations. Most SaaS teams don't realize the DSA applies to them.

## Root cause

The DSA defines a "recommender system" broadly (Article 3(s)): "a fully or partially automated system used by an online platform to suggest in its online interface specific information to recipients of the service, or prioritise that information, including as a result of a search initiated by the recipient of the service or otherwise determining the relative order or prominence of information displayed."

The key test: does automated logic influence *what* users see and *in what order* in a recipient-facing interface? If yes, you have a recommender system under the DSA.

## The 3-tier obligation structure

**Tier 1 — All Online Platforms (Article 27).** Any "online platform" — a hosting service that stores and disseminates information to the public at users' request. Includes B2C SaaS, marketplaces, community platforms, job boards, content-sharing tools. Micro-enterprises (fewer than 10 employees and turnover under €2M) are temporarily exempt.

**Obligation:** Publish at least one recommender system explanation in your Terms of Service or a dedicated policy. Cover the **main parameters** used in the system and the **relative importance** of those parameters to the user.

**Tier 2 — Very Large Online Platforms and Search Engines (VLOPs/VLOSEs, Articles 38-40).** 45M+ monthly active EU users, or designated by the Commission. Currently includes Amazon, Apple, Facebook, Google, Instagram, LinkedIn, Microsoft Bing, Pinterest, Snap, TikTok, Twitter/X, Wikipedia, YouTube, Zalando.

**Additional obligations:** Offer at least one recommender system option that is not based on profiling (i.e., a non-personalized, non-tracking-based alternative). Annual transparency report. Risk assessment. Data access for researchers.

## The 5 main parameters to disclose

Article 27 requires the platform to explain which of these categories apply and — crucially — their **relative importance**. Does recency outweigh engagement? Does a paid boost override organic signals? Typical parameters:

- **User behavior signals:** clicks, watch time, shares, comments, search history
- **Content metadata:** freshness, popularity, relevance to user query
- **Context signals:** time of day, device, location (with consent)
- **Business rules:** sponsored content, editorial picks, paid placement
- **Personalization:** based on user profile, demographic, inferred interests

For each parameter, disclose:

- Is it a **hard filter** (must be present/absent) or a **ranking signal** (influences score)?
- Is it **primary** (dominant weight) or **secondary** (tiebreaker)?
- Is it **dynamic** (learned from user behavior) or **static** (fixed rule)?

A ranked list with one-sentence weight descriptors per parameter satisfies Article 27 for most Tier 1 platforms.

## The non-profiling alternative (Article 38)

For VLOPs/VLOSEs, Article 38 requires at least one recommender option that is not based on profiling. This is a separate option from default personalization. Typically:

- **Chronological order** — most recent first
- **Reverse chronological** — oldest first (for content archives)
- **Alphabetical** — for product catalogs
- **Editor's picks** — curated by humans
- **Unranked** — flat list, no ranking

The alternative must be accessible "with equal prominence" — not buried in a settings submenu. A user-facing control next to the main feed is required.

## The 6-step compliance pattern

1. **Map every recommender surface.** Feed, search results, marketplace ordering, content suggestions, ranking modules, email digests. Each is a separate recommender system under the DSA.
2. **Document the parameter registry.** Internal document with each signal, its data source, its weight or role, when it was introduced or last modified. Not public, but available to regulators.
3. **Publish the main parameters policy.** Public-facing. Minimum content: purpose, list of main parameters with relative importance, user options for modifying preferences, how to access the non-profiling alternative, contact point.
4. **Implement the non-profiling alternative.** With equal prominence in the UI. Toggle or selector near the ranking surface.
5. **Align with GDPR.** ToS disclosure aligned with privacy notice; RoPA covers recommender signals.
6. **Review against EU AI Act Annex III.** If the system influences access to employment, credit, education, healthcare and exceeds SME thresholds, full Annex III obligations may apply.

## The 5 must-haves for the public policy

The DSA requires the disclosure to be in plain language. The minimum:

1. **Overview of the recommender system's purpose.** What does it recommend? Why?
2. **List of main parameters and their relative importance.** Hard filter vs ranking signal; primary vs secondary.
3. **User preference settings.** How can the user view and adjust their profile/preference signals?
4. **Non-profiling alternative.** How does the user access the option that is not based on profiling?
5. **Contact point.** Who answers questions about algorithmic decisions?

## The penalty

The DSA enforcement is national. Member State Digital Services Coordinators (DSCs) investigate and sanction. Penalties include fines up to 6% of worldwide annual turnover for the most serious violations (Article 74). For a global SaaS at €1B turnover, the maximum fine is €60M.

For VLOPs/VLOSEs, additional Commission enforcement applies, including periodic penalty payments of up to 5% of daily worldwide turnover.

## The EU AI Act overlap

The DSA and EU AI Act overlap for recommender systems:

- **DSA Article 27:** Transparency to users about main parameters
- **EU AI Act Article 50:** Transparency to users about AI interaction
- **EU AI Act Article 13:** Transparency to deployers about capabilities and limitations
- **EU AI Act Annex III:** Recommender systems in employment, credit, education, etc. are high-risk

A team deploying a recommender system in the EU may be subject to all four. The DSA is the broadest; EU AI Act is layered on top for high-risk uses.

## The 5-step evidence record

For DSA compliance, keep evidence:

1. **Recommender inventory:** Surface name, owner, recipient group, ranking objective, main criteria, whether the surface determines relative order
2. **ToS extract:** Article 27 main-parameter explanation + user modification options
3. **UI screenshots, design specs:** Showing where each choice is available
4. **For VLOPs/VLOSEs:** Article 38 non-profiling option + testing records
5. **Change log:** Tying recommender releases, ToS updates, UI changes to legal/product/data-science review

## Verification

The tell that DSA compliance is working:

- A recommender inventory is signed by the product owner
- The ToS or a dedicated policy describes main parameters and relative importance
- A non-profiling alternative is accessible with equal prominence
- Native European users see the same disclosures as marketing claims
- A regulator can request and receive the parameter registry within 30 days

The tell it isn't:

- "We're not subject to the DSA; we're a SaaS, not a social network"
- No public disclosure of ranking parameters
- The non-profiling alternative is buried in settings (or absent)
- A regulator request would take longer than 30 days to fulfill

## Gotchas

- **The DSA applies to more than VLOPs.** Most B2C SaaS with feeds, search, or recommendations is in scope.
- **"Recommender system" is broad.** Search results, "recommended for you," content feeds, product sorting, even "smart" autocomplete are recommender systems.
- **Article 27 does not require publishing the algorithm.** It requires plain-language disclosure of the main parameters and relative importance.
- **Micro-enterprise exemption is temporary.** Below 10 employees and €2M turnover is the threshold; growth revokes the exemption.
- **Non-profiling alternative must be "with equal prominence."** A toggle in account settings is not equal prominence; a toggle in the ranking surface is.
- **The DSA is enforced nationally.** Each Member State has a DSC; coordination is via the European Board for Digital Services.
- **The DSA is not the EU AI Act.** Compliance with one does not guarantee compliance with the other.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — EU AI Act
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `issues/gdpr-article-22-automated-decisions-2026.md` — automated decision rights
- `issues/ai-bill-of-rights-2026.md` — US counterpart

## Source URLs (verified 2026-08-10)

- https://sota.io/blog/eu-dsa-recommender-system-transparency-requirements-2026
- https://www.freshfields.com/en/our-thinking/blogs/technology-quotient/dsa-decoded-10-algorithmic-transparency-under-the-dsa-102mgg8
- https://www.sorena.io/artifacts/eu/digital-services-act/faq/recommender-transparency.md
- https://dsa-observatory.eu/2025/05/19/making-recommender-systems-work-for-people/
- https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems
