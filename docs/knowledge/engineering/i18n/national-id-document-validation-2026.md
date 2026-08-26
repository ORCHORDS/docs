# national-id-document-validation-2026

**Issue:** Products that collect government identifiers — national ID numbers, personal codes, tax IDs, passport numbers — for KYC, onboarding, or verification face a validation problem that is per-country by construction. Formats range from 10 to 18 characters, embed birthdates and gender (China's Resident ID), or carry modulo-11 or ISO 7064 check digits (Latvia, Brazil CPF, China). A single regex shipped worldwide rejects valid identifiers, accepts invalid ones, and frustrates users at the highest-friction step of onboarding. Because these numbers are PII with legal handling constraints, validation must also be designed around data minimization: validate format and checksum in the browser, transmit sparingly, mask in display, and log never.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What varies by country

1. **Structure and length.** China's Resident ID is 18 digits (17 plus a check character that can be X); India's Aadhaar is 12 digits with a Verhoeff check digit; Brazil's CPF is 11 digits with two modulo-11 check digits; EU personal codes range from Latvia's 11 digits (modulo-11 check) to Germany's 10-11 character tax format. No universal pattern exists; the rules must be a per-country data table.

2. **Embedded semantics.** Many identifiers encode birthdate and sometimes gender (Chinese, Nordic, and several Eastern European personal codes). This means format validation can also sanity-check the embedded date — and it means displaying or storing these numbers leaks more than an arbitrary ID, which raises the privacy stakes.

3. **Check-digit algorithms.** Modulo-10, modulo-11 (with different weight tables per country), Verhoeff, and ISO 7064 MOD 11-2 all appear. Reusing one country's checksum routine for another silently accepts mistyped numbers; the algorithm is part of each country's rule set.

4. **Official versus informal names.** The label users recognize differs per market (CPF in Brazil, SSN/SIN in North America, Aadhaar in India, NINO in the UK). Field labels must come from the localized strings, keyed by country, not a generic "Government ID" placeholder everywhere.

## Implementation approaches

1. **Use a maintained library instead of a regex table.** The Python idnumbers package, its id_validation sibling (40+ countries with demographic extraction), the JavaScript stdnum package (person, tax, and VAT identifiers), and the open-source Identique project (80 countries via format masks and check digits) encode this data and its corrections. Rolling your own table reproduces years of accumulated fixes badly.

2. **Key the rules off the country selector.** The form's country field should activate that country's format, input mask, checksum, and label. Validate progressively (length and charset while typing, checksum on blur or submit) and render errors in the user's language with the expected shape stated explicitly.

3. **Consider a verification API for high-stakes flows.** Format validation only proves plausibility. Vendors such as Socure and Trulioo validate national IDs against issuing-authority rules and, where available, authoritative data for KYC-grade assurance. Use them for onboarding money flows; format checks remain the fast client-side pre-filter.

4. **Handle partial and legacy formats.** Several countries have legacy numbering schemes still accepted by authorities (pre-2000 formats, region-coded older IDs). Ship allow-lists for documented legacy forms, and treat validation failure as a warning path with manual review when the cost of false rejection is a lost customer.

## Privacy and security requirements

1. **Validate locally where possible.** Client-side format and checksum validation catches fat-fingering without transmitting the number; only flows that genuinely require verification should send it to a server.

2. **Mask in every display context.** Show only the last 2-4 characters after entry (China Resident ID ***********123X style); full-number display is a compliance failure in most jurisdictions and an internal-leak risk. Masking must respect the locale's grouping conventions when any grouping is shown.

3. **Never log full identifiers.** Structured logging, crash reports, and analytics must redact these fields by key before persistence; a validation library that throws errors containing the input value needs a wrapping layer that scrubs.

4. **Scope data minimization and retention.** Store the number only if the product function requires it, encrypt at rest with restricted access, and document retention per jurisdiction (several regimes treat national IDs as special-category data). Validate-then-discard is often the compliant design.

## Testing strategy

1. **Fixture corpus of valid and near-miss invalid numbers.** For each supported country, test a valid number, each single-digit corruption of it (checksum must reject), wrong-length strings, and the documented legacy format. Generate corruptions programmatically so the checksum rejection rate is actually asserted.

2. **Cross-check embedded semantics.** For IDs encoding birthdates, assert that a mismatched birthdate is flagged where the product collects both, and that gender extraction (where offered) matches the issuing rules rather than assumed binaries.

3. **Test labels and masks per locale.** Screenshot the collection form in each UI locale and country combination, confirming the localized field name, helper text, input mask, and masked redisplay.

4. **Audit logging and error paths.** Attempt submissions with invalid numbers and verify no log line, error tracker payload, or analytics event contains the full value — the failure mode is invisible until a security review, so assert it in CI.
