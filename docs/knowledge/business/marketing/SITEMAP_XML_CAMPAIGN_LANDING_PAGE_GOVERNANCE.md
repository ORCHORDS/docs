# Sitemap XML Campaign Landing Page Governance

## Scope

This control governs XML sitemap inclusion, exclusion, update, validation, and retirement for campaign landing pages. It applies to pages created for paid media, email, social, partner campaigns, seasonal launches, webinars, trials, limited promotions, product announcements, and evergreen lead-generation programs. The control covers sitemap entries, sitemap indexes, canonical URL selection, last-modified evidence, campaign page lifecycle, validation testing, and correction handling. It does not guarantee crawling, indexing, ranking, rich results, traffic, or discoverability. Sitemap files are discovery signals for crawlers and must not be treated as a substitute for content quality, internal linking, robots controls, canonicalization, or platform-specific submission workflows.

The Sitemap protocol describes XML sitemap format requirements, including XML tags, UTF-8 encoding, entity escaping, required elements, and sitemap file limits: [Sitemaps.org, XML Sitemap Protocol](https://www.sitemaps.org/protocol.html). Google Search Central describes building and submitting sitemaps to Google and supports several sitemap formats: [Google Search Central, Build and submit a sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap). These primary sources are used for protocol and search-engine operational context. They are not used here to claim that a campaign URL will be indexed or that sitemap submission creates any specific search treatment.

## Required Fields And Controls

Every governed campaign landing page must have a page owner, canonical URL, campaign identifier, publication status, indexability intent, launch date, planned retirement date or review date, canonical tag status, robots directive status, and sitemap inclusion decision. A URL may be included in the campaign sitemap only if the canonical URL is stable, returns a successful response for the intended audience, is not blocked by robots controls for the relevant crawler, is not marked `noindex` when indexability is intended, and is approved for public discovery. A campaign page that is personalized, private, gated behind authentication, legally restricted, or meant only for paid click destinations may require exclusion.

Each sitemap `url` entry must contain a `loc` value with the canonical absolute URL. `lastmod` is required by this governance control when the team can derive it from a reliable content or deployment timestamp; if reliable timestamps are unavailable, the page should not invent dates. `changefreq` and `priority` are optional and should not be used as operational promises. If used, they must follow the protocol’s allowed value and range conventions and must be generated consistently, not tuned page by page to imply unsupported importance.

The sitemap must use UTF-8 encoding and escape XML-sensitive characters in URLs. Entries must not include tracking parameters, session identifiers, personal data, preview tokens, staging domains, internal hostnames, or campaign manager draft URLs. A campaign landing page may use UTM parameters in ads or email, but the sitemap entry must point to the clean canonical URL unless there is a documented architecture reason otherwise. Canonical URL selection must align with the page’s canonical link element, redirect target, hreflang cluster if present, and CMS slug.

## Workflow

The campaign page owner submits a sitemap decision as part of landing page launch. The request states whether the page should be discoverable through organic crawling, the reason for inclusion or exclusion, and the expected lifecycle. SEO or web operations reviews the request against page purpose. Public evergreen or product launch pages are usually candidates for inclusion. Short-lived paid acquisition variants, A/B test variants, duplicate audience-specific pages, and pages with sensitive targeting language are usually candidates for exclusion or consolidation under a canonical page.

When a page is approved, engineering or the CMS sitemap generator adds the canonical URL through the normal publishing pipeline. Manual sitemap edits are discouraged because they frequently introduce stale URLs or formatting defects. If a campaign requires rapid publication, the owner may request expedited sitemap generation, but the same validation evidence is required. When the campaign changes, the owner must update the page lifecycle record. Retirement may mean removing the URL from the sitemap, redirecting the page to an evergreen equivalent, leaving the page live but excluding it from sitemap discovery, or preserving it as an archive page with an accurate canonical state.

Sitemap indexes are used when the site has multiple sitemap files or large URL sets. Campaign landing pages may be grouped by site section, locale, brand, or content type. The grouping must be predictable so reviewers can find the relevant sitemap without scanning unrelated files. If multilingual or regional campaign pages exist, each localized canonical URL should be assessed independently because publication, availability, and indexability intent may differ by region.

## Validation Evidence And Tests

Pre-launch validation must confirm that the landing page URL returns the expected status code, resolves to the canonical URL, does not redirect to a staging or parameterized URL, and displays the approved content. The sitemap file must parse as XML, use the correct namespace, include the approved `loc`, and avoid duplicate entries. The validation must check escaping of ampersands and special characters, absence of UTM parameters, absence of session identifiers, and consistency between sitemap `loc` and page canonical tag. If `lastmod` is present, the reviewer must verify that it comes from a meaningful content or deployment timestamp rather than the time the sitemap job last ran.

Post-launch validation should fetch the sitemap from the production URL and verify the campaign entry after deployment, not only in build output. Search console submission or ping workflows may be recorded where the organization uses them, but submission evidence should be separated from protocol validity. Monitoring should flag broken sitemap URLs, redirects, noncanonical sitemap entries, `noindex` pages included in sitemaps, robots-blocked included URLs, pages missing expected sitemap inclusion, and pages still listed after their retirement date.

Evidence must include the inclusion decision, approved canonical URL, rendered page check, sitemap parser result, robots and canonical checks, `lastmod` basis if used, and correction history. For generated sitemap systems, evidence may be a release artifact, CMS record, crawl report, or automated test output. The goal is to prove the URL was intentionally included and technically valid at the time of release, not to preserve every crawler interaction.

## Failures And Corrections

Common failures include adding ad URLs with UTM parameters, listing redirected vanity URLs instead of final canonicals, leaving expired campaign pages in the sitemap, using current timestamps for unchanged pages, publishing staging URLs, and including pages that are marked `noindex`. Another failure is omitting high-value evergreen campaign pages because the sitemap generator excludes a new content type. These defects are corrected by updating the sitemap generation rule, page metadata, or canonical configuration and then revalidating the production sitemap.

If a sitemap contains a private or sensitive URL, the immediate correction is to remove it from the sitemap, assess whether the URL was publicly accessible, and involve privacy, security, or legal owners if the exposure exceeds SEO operations. This control does not decide notification duties. It requires factual containment and evidence: when the URL was added, when it was removed, whether it returned public content, and which logs or crawler tools observed it.

If a page was intentionally excluded but stakeholders later want organic discovery, the correction is not simply to add it to the sitemap. The owner must confirm that copy, claims, canonicalization, robots directives, regional availability, and lifecycle plans are appropriate for public discovery. Conversely, if a campaign has ended but traffic still relies on the URL, removal from the sitemap should be coordinated with redirects and reporting annotations.

## Requirements Versus Recommendations

Required: use clean canonical URLs; exclude tracking parameters and secrets; validate XML syntax and namespace; align sitemap entries with canonical and robots directives; document inclusion decisions; use truthful `lastmod` values or omit them; remove or redirect retired campaign pages according to lifecycle records; and correct sitemap defects with evidence.

Recommended: automate sitemap generation from CMS metadata; maintain campaign page lifecycle states; run scheduled crawls; group campaign URLs predictably; review sitemap entries during campaign retrospectives; and create alerts for `noindex` or redirected URLs appearing in sitemaps.

## Limitations

A sitemap helps crawlers discover URLs, but it is not a command to index, rank, retain, or refresh a page. Crawlers may discover pages through other links even if they are excluded from the sitemap, and they may ignore optional metadata. Sitemap governance improves technical hygiene and campaign lifecycle control, but it does not replace robots governance, canonical strategy, content review, accessibility testing, claim substantiation, or privacy assessment.

## Canonical sources

- **Primary authority 1 — Sitemaps.org, XML Sitemap Protocol:** [https://www.sitemaps.org/protocol.html](https://www.sitemaps.org/protocol.html)
- **Primary authority 2 — Google Search Central, Build and submit a sitemap:** [https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
