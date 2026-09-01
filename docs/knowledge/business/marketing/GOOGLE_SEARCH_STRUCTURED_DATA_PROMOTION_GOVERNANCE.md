# Google Search Structured Data Promotion Governance

## Scope

This control applies to promotional web pages, product pages, offer pages, coupon pages, review pages, event pages, recipe pages, article pages, local-business pages, job pages, FAQ-like content, video pages, and campaign landing pages where structured data may affect Google Search eligibility, appearance, or interpretation. It covers JSON-LD, Microdata, RDFa, schema generation, CMS plugins, ecommerce feeds, product information management systems, review widgets, affiliate content, and agency-created markup.

The purpose is to prevent marketing teams from using structured data in ways that misrepresent page content, create search policy risk, or produce invalid markup. This document does not guarantee rich results, ranking improvement, indexing, display, or eligibility. Google decides whether and how to use structured data. Canonical primary references include Google Search Central’s [structured data general guidelines](https://developers.google.com/search/docs/appearance/structured-data/sd-policies) and Google Search Central’s [structured data feature guide](https://developers.google.com/search/docs/appearance/structured-data/search-gallery).

## Requirements Versus Recommendations

Required controls:

- Structured data must describe content visible or otherwise available to users on the page.
- Markup must use supported properties for the selected feature and must not include false, misleading, promotionally inflated, or hidden claims.
- Review, rating, price, availability, event date, coupon, job, and product fields must be sourced from approved systems of record.
- Markup changes must be tested before deployment and monitored after deployment.
- Pages using structured data must comply with Google’s general structured data guidelines and the feature-specific guidance selected by SEO or engineering.
- Evidence must show the rendered page, generated markup, validation result, source data, deployment version, and correction history.

Recommended controls:

- Use JSON-LD unless the site architecture has a documented reason for another format.
- Generate markup server-side or during build when possible so it is stable for crawlers.
- Keep one owner for each schema type and avoid duplicate plugin output.
- Use Google Search Console enhancement reports and URL inspection as monitoring inputs, without treating them as complete coverage.

## Governance Model

SEO owns schema strategy. Content owns page truth. Product or merchandising owns price, availability, SKU, and offer data. Engineering owns implementation. Legal or compliance reviews regulated claims, endorsements, comparative language, and disclosures. Agencies may propose markup but may not ship it without internal approval.

Each structured data type must have a control profile. A profile identifies the feature objective, page templates, required fields, recommended fields, source systems, transformation rules, validation tools, owner, and review cadence. For example, Product markup may draw name, image, SKU, brand, price, currency, availability, and aggregate rating from ecommerce systems. Event markup may draw event name, start date, location, attendance mode, and ticket offers from the event platform. Review markup must not be generated from testimonials that do not meet the applicable Google guidance for the feature.

## Workflow

The workflow starts with a schema request. The requester identifies page type, URL patterns, business purpose, desired search appearance, proposed structured data type, source data, and launch date. SEO confirms whether the requested type is relevant and whether Google documents a corresponding feature. If no supported feature exists, the team may still use schema.org markup for machine readability, but the request must not be sold internally as a guaranteed Google rich-result tactic.

Content and product owners then confirm that every marked-up claim appears on the page or is available in a user-facing way. Engineering maps fields to source systems and documents fallback behavior. If a required field is missing, the page must omit the markup or omit the affected object rather than fill placeholders. If a field is estimated, promotional, or manually overridden, the data owner must approve it.

Before deployment, QA validates the rendered URL or staging equivalent. The test must inspect final HTML after templates, plugins, tag managers, hydration, and personalization have run. QA must check for duplicate objects, stale offers, invalid dates, broken image URLs, mismatched canonical URLs, and structured data that describes content not present on the page.

After deployment, SEO monitors Search Console, crawl logs where available, structured-data validation tools, and page-change alerts. Issues are triaged as syntax, eligibility, policy, source-data, rendering, or content mismatch.

## Concrete Fields And Controls

Schema governance fields:

- `schema_profile_id`: stable profile identifier.
- `schema_type`: Product, Offer, Event, Article, LocalBusiness, VideoObject, BreadcrumbList, FAQPage, or other.
- `url_pattern`: templates covered.
- `business_object_id`: SKU, event ID, article ID, location ID, or page ID.
- `source_system`: CMS, ecommerce platform, PIM, review system, event platform, or manual.
- `required_properties`: properties required by the selected feature guidance.
- `recommended_properties`: optional properties approved for use.
- `visible_content_mapping`: where each marked-up claim appears to users.
- `claim_owner`: accountable team for factual accuracy.
- `validation_tool_result`: pass, warning, fail, or not eligible.
- `deployment_version`: release or CMS version.
- `last_reviewed`: timestamp and reviewer.
- `exception_id`: approved deviation, if any.

Controls must prevent common SEO misuse. Product price markup must match the page price and currency shown to users. Availability must update when inventory changes. Review counts and ratings must come from the approved review system and must not be manually inflated. Event dates must be real dates, not rolling placeholders. Coupon or offer validity must not be extended in markup after the visible offer expires. FAQ markup must not be used to hide promotional copy that users cannot see.

The implementation must avoid duplicate conflicting markup from plugins, themes, and custom code. If multiple systems produce schema, engineering must designate a primary generator and disable redundant output. Pages with personalization must not generate markup that varies unpredictably by user unless the page content and canonical URL support that variation.

## Validation Evidence And Tests

Validation evidence includes rendered HTML, extracted JSON-LD or other markup, source-system records, screenshots of visible content, test results, deployment version, and monitoring output. Evidence must be tied to a URL and timestamp because promotional content changes frequently.

Tests must include:

- Visibility test: verify each marked-up claim appears on the page or is otherwise user-accessible.
- Required-field test: compare markup with Google’s feature-specific required properties.
- Source-of-truth test: trace price, rating, availability, date, location, and author fields to approved systems.
- Rendered-output test: inspect the final rendered page, not only template source.
- Duplicate-markup test: detect multiple conflicting structured data objects.
- Expiration test: verify offers, coupons, jobs, and events are removed or updated after expiry.
- Image test: verify image URLs are crawlable and match the content object.
- Validation-tool test: run Google’s relevant structured-data testing or rich-results tooling and preserve output.
- Search Console test: review enhancement or issue reports after deployment where available.

Primary references for test criteria should include Google Search Central’s [structured data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies), the [Search Gallery of supported structured data features](https://developers.google.com/search/docs/appearance/structured-data/search-gallery), and the Google Search Central guide to [using structured data](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data).

## Failures And Corrections

Common failures include marking up content hidden from users, using Product markup on category pages without a specific product focus, preserving expired offer prices, marking fake aggregate ratings, letting multiple plugins emit conflicting schema, using FAQ markup for advertising claims, or copying markup from a competitor without checking Google’s current guidance.

Corrections must start with page truth. If the page does not support the claim, remove the markup or revise the page through normal content approval. If source data is stale, fix the integration and regenerate affected pages. If a plugin emits duplicate or inaccurate markup, disable it for the affected templates. If a manual override caused the failure, restrict override permissions and require approval for future changes.

For policy-sensitive failures, SEO must document affected URLs, dates active, source of the inaccurate field, corrective release, and monitoring result. A sample of corrected URLs must be revalidated. If Search Console reports issues after correction, the owner may request validation in Search Console where appropriate, but the request must be based on verified page fixes rather than cosmetic markup edits.

## Limitations

Structured data is a communication layer, not a ranking entitlement. Passing a validation tool does not mean Google will show a rich result, and warnings do not always mean a page is ineligible. Search behavior, feature availability, and documentation can change. Teams must use current Google Search Central documentation when approving a new schema profile.

This control does not cover every search-engine, marketplace, social-card, or feed requirement. It also does not approve deceptive promotional claims. The approved internal statement is narrow: the structured data for the identified pages was mapped to visible content and approved source systems, tested against Google Search Central guidance, and monitored as of the review date.

## Canonical sources

- **Primary authority 1 — structured data general guidelines:** [https://developers.google.com/search/docs/appearance/structured-data/sd-policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)
- **Primary authority 2 — structured data feature guide:** [https://developers.google.com/search/docs/appearance/structured-data/search-gallery](https://developers.google.com/search/docs/appearance/structured-data/search-gallery)
- **Primary authority 3 — using structured data:** [https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data)
