# CISA: Default Passwords Are a Product Design Failure

**Issue:** A product ships with a universal or well-known default password and relies on every customer to remember to change it before exposure.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

CISA's Secure by Design guidance places responsibility for secure defaults on the manufacturer rather than treating insecure defaults as a customer configuration problem. CISA and partner agencies repeatedly recommend eliminating default passwords; examples include using a random initial credential or requiring secure credential setup on first use. The January 2025 Product Security Bad Practices update is voluntary guidance aimed especially at software manufacturers supporting critical infrastructure, while encouraging all software manufacturers to avoid the identified bad practices.

## Engineering rule

- Do not ship one reusable password across product instances, tenants, appliances, or installations.
- Prefer a unique initial credential, a secure first-run enrollment process, or another design that prevents a known default from granting access.
- Make secure setup part of the product lifecycle instead of relying on documentation that tells customers to harden an insecure starting state.
- Treat remote and administrative access as particularly sensitive to insecure credential defaults.
- Review manufacturing, recovery, reset, test, and support paths so a default credential is not reintroduced outside the normal setup flow.

## Verification

- Provision two clean product instances and confirm they cannot authenticate with the same manufacturer-supplied default credential.
- Search product images, configuration defaults, deployment templates, documentation, and support procedures for reusable default passwords.
- Factory-reset or reinstall a test instance and confirm the reset path does not restore a universal credential.
- Verify secure first-run setup cannot be skipped when the product would otherwise expose authenticated functionality.

## Official sources

- CISA/FBI, Product Security Bad Practices update, January 17, 2025: https://www.cisa.gov/news-events/alerts/2025/01/17/cisa-and-fbi-release-updated-guidance-product-security-bad-practices
- CISA, Secure by Design manufacturer guidance on eliminating default passwords: https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-335a
