# Schema.org Offer Markup Validation

## Scope

This control governs the validation of `schema.org` `Offer`, `AggregateOffer`, and offer-related structured data on marketing landing pages, product pages, promotional pages, and campaign pages. It applies when markup is used to describe a product, service, event ticket, subscription, downloadable item, bundle, promotion, or other commercial offer. The control covers field selection, alignment with visible page content, publication workflow, validation evidence, monitoring, and correction. It does not guarantee search result features, ranking treatment, merchant eligibility, or compliance with consumer protection, pricing, tax, sector-specific, or marketplace laws.

Schema.org defines `Offer` as a type for offers to provide an item, including examples such as selling a product, renting a DVD, performing a service, or giving away tickets: [Schema.org, Offer](https://schema.org/Offer). Google Merchant Center documents supported structured data attributes and states that certain `Offer` properties are nested within a `Product` through the `offers` property for merchant use cases: [Google Merchant Center Help, Supported structured data attributes and values](https://support.google.com/merchants/answer/6386198). These are primary references for vocabulary and Google merchant interpretation, not broad claims that all search engines or platforms will use markup in the same way.

## Required Fields And Controls

Every governed page with offer markup must have a canonical page URL, page owner, offer owner, product or service identifier, pricing source, publication status, and last validation date. The structured data must identify the offered item through a `Product`, `Service`, `Event`, or other relevant type before attaching `offers` unless the page pattern has a documented reason to publish a standalone `Offer`. The required offer fields are determined by the page type, but the governance baseline requires review of `@context`, `@type`, `url`, `price` or price explanation, `priceCurrency` when a numeric price is present, `availability` when availability is represented, and `seller` or provider identity when the page context does not clearly establish the seller.

Concrete field controls include using `https://schema.org` terms, representing a single current offer as `Offer`, representing a range or multiple sellers as `AggregateOffer` only when the page visibly supports that meaning, and avoiding stale or hidden promotional claims in markup. `price` must match the visible price basis on the page, including whether the price is from, starting at, per month, per unit, discounted, or conditioned on a term. If a page displays tax, shipping, or fee information outside the headline price, markup must not imply a cleaner or broader price than the page supports. `priceValidUntil` should be used only when the team has a maintained expiration source; otherwise it can become a stale assertion.

`availability` must reflect the page’s actionable state. A page that collects waitlist signups should not be marked as a normal in-stock purchasable offer unless the page also enables immediate purchase. `itemCondition` must not be used to improve appearance if the item condition is not visible or applicable. `seller` should identify the selling entity, not the agency, affiliate, or analytics vendor that manages the campaign. `sku`, `gtin`, `mpn`, and brand identifiers are recommended where the business maintains authoritative product identifiers and the visible page or feed strategy depends on them.

## Workflow

Offer markup begins with a content and commerce source review. The page owner identifies the authoritative pricing system, promotion rules, inventory or booking source, product catalog record, and seller entity. The structured data implementer maps those sources into JSON-LD or another approved syntax. JSON-LD is preferred for maintainability when the site already uses it, but the control is syntax-neutral if the resulting markup is valid and maintainable.

Before publication, the implementer compares the proposed markup with the visible page. This includes price, currency, availability, product name, variant, seller, offer URL, condition, and promotion window. Marketing operations verifies that campaign-specific copy does not cause the markup to describe a broader offer than the page provides. Engineering verifies that server-side rendering, client-side hydration, tag managers, and personalization rules do not create conflicting offer objects for the same page state.

Release approval requires a validation record. The record contains the page URL, rendered HTML source or structured-data extraction, validator output, manual field comparison, source systems checked, known limitations, and approver. Pages generated from templates may use representative samples, but samples must include each material variation: currency, region, free trial, sale price, out-of-stock state, preorder state, subscription term, bundle, and discontinued item where those states exist.

## Validation Evidence And Tests

Validation must test both syntax and semantic alignment. Syntax evidence includes parsing JSON-LD as valid JSON, checking required `@context` and `@type` values, ensuring URLs are absolute where appropriate, and confirming that structured data extraction tools can identify the intended `Offer` object. Semantic evidence includes a field-by-field comparison against visible page content and authoritative commerce data. A valid parser result is not enough if the markup says an item is available at a price the page does not show.

Automated tests should inspect generated pages for duplicate conflicting offer nodes, missing currency for numeric prices, malformed dates, invalid URLs, blank `price`, noncanonical offer URLs, and hard-coded stale values. Template tests should verify that sale prices revert after promotion end, region-specific currency does not leak into other locales, and unavailable products do not retain purchasable availability markup. Monitoring should sample production pages and compare markup to product feed or catalog values. A discrepancy threshold should trigger review before the discrepancy becomes a reporting or platform issue.

Evidence should include screenshots or rendered text snapshots when page personalization affects the offer. If a user segment, geography, or logged-in status changes the visible price, validation must identify which state the markup represents. If the site cannot reliably align structured data with personalized offers, the safer correction may be to remove or simplify offer markup for those states until the rendering model is dependable.

## Failures And Corrections

Common failures include hard-coded old sale prices, missing `priceCurrency`, use of `AggregateOffer` for a single seller, markup for an offer not visible on the page, multiple products on one page with ambiguous offers, and stale `availability`. Another common failure is publishing a campaign landing page that visually advertises a discount while structured data retains the standard price. This creates inconsistent machine-readable and human-readable claims and must be corrected by updating the markup, changing the page, or removing the offer object.

If validation finds a mismatch before launch, publication is blocked until the owner resolves the underlying source. If a mismatch is live, the correction owner records the affected URL, field, detected value, correct value, time discovered, time corrected, and cause. Corrections should be deployed through the same template or data source that created the problem; one-off edits are allowed only for urgent containment and must be replaced by a durable fix. When a platform has already crawled bad data, the owner may request recrawl or resubmission where supported, but this document does not promise timing or outcome.

If a page intentionally omits structured data because the offer is too conditional, too personalized, or not yet stable, that omission should be documented. Absence of markup is often preferable to inaccurate markup. If legal or pricing teams dispute the interpretation of an offer field, the page must not publish broader machine-readable claims while that dispute is unresolved.

## Requirements Versus Recommendations

Required: keep offer markup consistent with visible page content; use supported Schema.org terms; validate syntax and field alignment before launch; avoid hidden, stale, or broader claims in markup; document source systems; test major template variations; and correct production mismatches with an evidence trail.

Recommended: centralize offer markup generation in the commerce or CMS layer; use product identifiers when authoritative; monitor production pages against catalog data; include structured data validation in release checks; and maintain examples for common page types such as sale, preorder, out-of-stock, subscription, and bundle pages.

## Limitations

Structured data is a machine-readable description, not an independent offer contract, advertising approval, or guarantee of platform display. Search engines and commerce platforms may ignore, reinterpret, or place additional requirements on markup. This control addresses accuracy, consistency, and operational validation; it does not replace pricing review, tax review, accessibility review, consumer disclosure review, or platform-specific merchant onboarding.

## Canonical sources

- **Primary authority 1 — Schema.org, Offer:** [https://schema.org/Offer](https://schema.org/Offer)
- **Primary authority 2 — Google Merchant Center Help, Supported structured data attributes and values:** [https://support.google.com/merchants/answer/6386198](https://support.google.com/merchants/answer/6386198)
