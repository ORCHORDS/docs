# Marketing Localized Price Display

A localized storefront makes an unspoken promise with every price it renders: that the amount shown is the amount the customer will actually be charged, in a currency the customer recognizes, with taxes and fees presented honestly. When localization fails, it fails silently: a dollar price shipped to a euro market, a rounded price that no longer matches the charged amount, a tax-exclusive price landing where tax-inclusive display is expected. This article governs currency, rounding, and tax-inclusive display discipline for localized marketing surfaces.

## Scope

This control covers price presentation on localized versions of marketing and commerce properties: geo-targeted landing pages, localized product pages, regional email campaigns, price fields in ad extensions and product feeds, promotional pricing, and currency-displayed checkout communications. It governs the currency code applied, the rounding of converted amounts, the treatment of fractional units, tax-inclusive versus tax-exclusive presentation, and the consistency between displayed and charged amounts.

It does not govern price-setting strategy, reference-price honesty, or the completeness of tax determination logic itself; those are separate concerns. Its question is representational fidelity: does the displayed price state its currency, round consistently, and disclose its tax basis such that a reasonable customer is not surprised?

## Workflow or implementation guidance

1. **Bind display currency to a single decision source.** The currency shown for a session derives from one documented rule chain: customer-selected currency, then storefront locale, then geo signal, in a defined precedence order. Every price render path consumes the resolved currency from that source; no template or feed writer hardcodes a symbol.
2. **Carry the ISO 4217 code, render the symbol deliberately.** Internally, prices are stored with an ISO 4217 currency code and a decimal precision appropriate to the currency's minor unit. Rendering maps code to symbol and position using locale-aware formatting, because the same currency places its symbol differently across locales, and some currencies share a symbol while differing in value.
3. **Respect minor units and rounding rules.** Currencies without widely used fractional units display integer amounts; currencies with fractional units round to the minor unit under a documented rule. Rounding happens at a defined point in the pipeline, once, and the rounded value is what flows to checkout, so display and charge cannot diverge.
4. **Decide tax-inclusive display per market, and label it.** Each storefront market carries a tax-display mode: prices including applicable taxes, or excluding taxes to be added at checkout. Where display is tax-exclusive in a predominantly inclusive market, or vice versa, the basis is disclosed near the price, following the disclosure placement discipline. Promotional prices follow the same mode as base prices.
5. **Round promotions coherently.** Percentage and fixed-amount promotions are computed before final rounding, not applied to an already-rounded display string, and the resulting promotional price is rounded under the same rule as the base price. "40% off" badges must reconcile with the displayed pair.
6. **Keep feeds and extensions synchronized.** Product feeds, ad extensions, and email templates consume the same resolved price service as the storefront, with the currency and tax mode stamped per destination. A feed generated in one currency and displayed in another is a defect.
7. **Verify by market on a schedule.** An automated monitor fetches representative pages per market, extracts the rendered price, and checks currency correctness, minor-unit format, tax-mode label presence, and agreement with the price service.

## Controls

- The currency resolution rule chain is versioned and owned; precedence changes are reviewed changes.
- Price rendering is centralized in formatting utilities that consume the ISO 4217 code, with direct symbol interpolation in templates flagged by lint rules.
- The rounding rule is documented per pipeline and applied exactly once; audit tests assert that displayed, fed, and charged amounts agree to the minor unit.
- Market tax-display modes are configuration, not copy; changing a market's mode triggers re-verification of that market's surfaces and communications.
- Locale data updates, including currency and pluralization changes, are consumed on a schedule with regression checks, because symbol and format changes do arrive.
- Geo-derived currency never overrides an explicit customer selection during a session, preventing mid-session currency flips that strand a stale amount.

## Validation evidence

- Market capture sets: rendered price fields with resolved currency, format, symbol position, and tax-basis label, captured by the monitor across a representative market sample.
- Reconciliation output showing display, feed, and charged amounts matching to the minor unit for sampled transactions in each currency.
- Rounding-rule documentation and test vectors covering the currencies in active use, including minor-unit edge cases.
- Tax-display mode configuration export per market, matched against the labels actually rendered.
- Change records for locale-data updates and their regression results.
- Session recordings or logs demonstrating precedence behavior when a customer's selection conflicts with geo.

## Failure modes and correction

Common failures include a US dollar price rendered unchanged in a market expecting local currency, a converted price rounded in the template so checkout shows a different final figure, tax-exclusive display shipped to a market where inclusive display is the norm without a label, a percentage-off badge computed from a pre-rounding base so the displayed pair is arithmetically inconsistent, feeds stamped with the storefront's currency rather than the destination's, and a mid-session currency change silently repricing an open cart. Each of these produces customer surprise, the outcome this control exists to prevent.

Correction fixes the rendering path, not the individual page: the affected market, surface, and date range are identified from monitor captures, the pipeline defect is corrected at the utility or feed generator, and the market is re-verified before the change is considered closed. Where customers were charged an amount inconsistent with display, the discrepancy is quantified and remediation decided with finance. Feed defects trigger re-submission to affected destinations. Recurrence hardens the lint rules and the monitor's coverage.

## Limitations

Currency display conventions vary by locale in ways that shift over time, and no internal rule set guarantees acceptance in every market; some markets impose statutory price-display duties stricter than this control, including unit pricing and fee-inclusive quotation requirements that are out of scope here. Tax determination correctness, payment-processor currency conversion, and local consumer-law pricing rules are governed elsewhere. Symbol-sharing currencies and minor-market locale data edge cases remain residual risks that monitoring detects rather than eliminates.

## Canonical sources

- **Primary authority 1 — Unicode Technical Standard #35 (CLDR), Part 3: Numbers, currency and currency formats:** [https://www.unicode.org/reports/tr35/tr35-numbers.html](https://www.unicode.org/reports/tr35/tr35-numbers.html)
- **Primary authority 2 — ISO 4217, Codes for the representation of currencies (currency code standard):** [https://www.iso.org/iso-4217-currency-codes.html](https://www.iso.org/iso-4217-currency-codes.html)
- **Reference — W3C, Internationalization Techniques: Authoring HTML (language and locale handling):** [https://www.w3.org/International/techniques/authoring-html](https://www.w3.org/International/techniques/authoring-html)
