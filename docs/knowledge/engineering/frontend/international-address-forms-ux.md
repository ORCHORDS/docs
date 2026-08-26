# international-address-forms-ux

**Issue:** Address entry forms built for US users (two street lines, city, state dropdown, 5-digit ZIP) fail almost everywhere else: they impose fields that do not exist in the destination country, force postal codes where some countries have none (about 70+ territories lack them), and validate against formats that reject valid addresses. The W3C internationalization guidance ("Address formats around the world") is blunt: there is no single international address layout, and rigid field structures are the root cause of failed signups and undeliverable shipments. Getting this right matters commercially — checkout abandonment and delivery failures track directly to address form friction — and it is a multi-layer problem: field model, per-country adaptation, validation strategy, autocomplete assistance, and accessibility of the adaptive layout.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Field Model and Country-First Layout

1. **Ask for the country first.** The country selector belongs at the top of the form, not the bottom, because every subsequent field (which fields exist, their labels, their order, their validation) derives from it. This is the consensus across W3C i18n guidance, the JPMorgan Salt design system's international address form pattern, and UX Planet's field design best practices: adapt fields dynamically for the chosen country instead of showing one rigid layout.

2. **Model fields as country-driven configuration, not hardcoded JSX.** Define a schema per country (or per format family) listing fields, labels, required flags, input types, and expected order. The form component maps over the schema; adding a new country is data, not code. Google's Address Data (libaddressinput) provides exactly this dataset — field ordering and requirements per region, used by Android and Chrome autofill — and is the standard source rather than hand-maintained country lists.

3. **Use neutral labels for shared fields.** "Address line 1/2" beats "Street"/"Apt" as universal labels; "State/Province/Region" adapts per country. W3C's guidance emphasizes avoiding field labels that assume a US structure: many countries put the apartment number before the street, others write the district before the city, and about a dozen countries place the postal code before the city (e.g., France, Japan, Brazil).

4. **Keep an optional extra line everywhere.** A flexible second (and on request third) address line catches unit numbers, landmarks, and delivery instructions that structured fields would otherwise reject. Rigid validation that refuses valid-but-unusual content is the top complaint in UX Matters' analysis of international address fields.

## Country-Specific Adaptation

1. **Adapt field presence, not just labels.** Examples that break naive forms: UK addresses frequently need a county-free layout with postcode last; Japanese addresses are ordered prefecture → city → ward/subarea → block → building, best entered in that order (or as a single line in Western order); Chinese addresses go largest-to-smallest (province, city, district, street, building); Irish Eircodes and Canadian alphanumeric postcodes have their own casing rules. The Salt design system pattern demonstrates dynamic field display per country with smooth transitions.

2. **Localize per-locale, not just per-country.** Language choice (the user's UI locale) and country choice (the destination) are independent: a Japanese address entered by an English speaker still needs romanized labels but Japanese field structure. Separate "address country" from "form language" in your model — conflating them produces forms that switch language when the user picks a country.

3. **Handle RTL and name-order gracefully.** For RTL locales, mirror the layout and let the browser's dir attribute drive field alignment; never hardcode left-aligned inline groups. Display formatting of the captured address back to the user (and on shipping labels) must follow the destination country's conventions — storing structured data and rendering per-country formatted output beats storing a pre-formatted string.

4. **Animate the adaptation without losing entered data.** When the country changes, fields appear/disappear and relabel; preserve overlapping values (the address lines usually survive) rather than wiping the form. Announce the structural change politely for screen reader users (see Accessibility below).

## Validation and Address Services

1. **Validate postal codes against country-specific patterns only.** ZIP+4, UK postcode, Canadian A1A 1A1, and Japanese 7-digit formats are all different; and roughly 70+ territories have no postal code at all, so a required postal code field must itself be country-conditional. Per-country regexes from libaddressinput or CLDR cover the mainstream; treat pattern failure as a warning ("did you mean...") rather than a hard block where deliverability is not critical.

2. **Use an address validation API for high-stakes flows.** Google's Address Validation API (part of Maps Platform) validates and standardizes addresses across 240+ countries/regions, returning formatted output, resolved components, and a validity verdict with granularity (down to premises level). Recommended integration posture from its docs: validate on submit, show the standardized version back to the user to confirm, and keep user-edited input when they override the suggestion — never silently rewrite what the user typed.

3. **Never hard-block on validation failures.** Many perfectly deliverable addresses (new buildings, informal addressing in emerging markets, diacritics variants) fail structured validation. Design the fallback path: warn, let the user proceed, and flag the record for manual review downstream. Blocking checkout on a validator false-negative costs more than an occasional mis-delivery.

4. **Validate on blur and on submit, not per keystroke.** International fields frustrate early validation (a half-typed UK postcode always looks invalid). Communicate missing required fields per the country schema on submit, and use inline errors that reference the localized label actually shown.

## Autocomplete and Entry Assistance

1. **Autofill first, autocomplete second.** Give every field correct autocomplete tokens (autocomplete="address-line1", "address-line2", "country", "postal-code", plus the newer "address-line3", street-address, and one-time-code-adjacent tokens where relevant) so browsers can fill saved addresses. Native autofill is free, private, and already internationalized — it outperforms any custom widget for returning users.

2. **Offer address autocomplete cautiously outside structured countries.** Google Places autocomplete works excellently for US/UK-style structured addresses, but Vitaly Friedman's UX guidance warns it frustrates users in countries with unstructured or unfamiliar-to-the-provider addressing: candidates feel random, and users cannot enter what the provider does not know. If you offer search-as-you-type, always keep a visible "Enter address manually" escape hatch that does not require dismissing a modal.

3. **Confirm the geocoded result, keep the typed truth.** When the user picks an autocomplete suggestion, populate structured fields and show them editable. Do not auto-correct the user's typed input on blur to the suggestion — the canonical cause of "wrong apartment" support tickets is a widget silently replacing user text.

## Accessibility and Edge Cases

1. **Announce dynamic field changes.** Because the form reshapes when the country changes, associate a polite live region summarizing the change ("Form updated for Japan: 6 fields") and move focus predictably — not forcibly. Screen reader users must never have fields silently appear or vanish mid-entry without notification.

2. **Label programmatically, not by placeholder.** Placeholders disappear on input and fail contrast and translation norms; every adaptive field needs a persistent visible label wired via for/id, plus aria-describedby for per-field hints like postal code formats.

3. **Test with real world data.** Fuzz the form with: addresses without postal codes (Hong Kong, UAE, many African territories), maximum-length UTF-8 input (Thai and Arabic street names), apostrophes and hyphens (O'Brien, Saint-Étienne), and country switching after full entry. Each of these breaks a common naive implementation, and each corresponds to a real support ticket class.
