# CISA: Baseline MFA and Admin Defaults Belong in the Product

**Issue:** A product technically supports MFA but leaves privileged users on password-only authentication unless each customer discovers, purchases, or manually enables a stronger option.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Secure by Design guidance urges manufacturers to make security outcomes easier for customers rather than shifting the burden downstream. CISA and NSA have specifically urged manufacturers to support MFA, ideally phishing-resistant MFA for privileged users, and to make MFA a default rather than opt-in feature. CISA has also stated that basic security capabilities needed to operate a product securely should not require additional fees. These are secure-by-design recommendations, not a universal legal rule for every product.

## Engineering rule

- Design privileged/admin authentication so MFA is available as a baseline product capability.
- Prefer secure defaults that require or strongly establish MFA for privileged access rather than leaving password-only admin access as the effortless path.
- Support phishing-resistant methods where the product's risk and platform capabilities allow them.
- Do not make a customer's ability to protect privileged access depend solely on purchasing a higher commercial tier.
- Treat deployment templates, first-run setup, recovery, and account bootstrap as part of the MFA design, not exceptions to it.

## Verification

- Create a new privileged account using the default product path and record whether MFA is required, prompted, or silently optional.
- Verify the baseline product tier exposes the security capability needed to protect privileged users.
- Test recovery and bootstrap paths to confirm they do not bypass the intended privileged-user MFA policy.
- Review product claims so “supports MFA” is not used to imply “secure by default” when the default remains password-only.

## Official sources

- NSA/CISA, Top Ten Cybersecurity Misconfigurations — Secure by Design recommendations for manufacturers: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-278a
- CISA, manufacturer guidance supporting MFA including phishing-resistant methods and secure-by-default operation: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-335a
- CISA/FBI, Product Security Bad Practices update, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
