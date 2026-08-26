# ccpa-data-broker-registration

**Issue:** California data broker annual registration requirements under Civil Code 1798.99.80
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
California law requires data brokers to register with the California Privacy Protection Agency (CPPA) by January 31 each year. The definition of data broker is broad: any business that sells personal information about consumers with whom it has no direct relationship.

## Pattern / Solution
Who must register:
- For-profit businesses
- Subject to CCPA
- Core activity = selling PI of consumers without a direct relationship

Registration steps:
1. Create account at CPPA data broker registry portal (cppa.ca.gov)
2. File by January 31 (covers prior calendar year)
3. Pay $600 annual fee
4. Disclose: categories of PI sold, whether health/reproductive data is included, opt-out link

Ongoing obligations:
- Maintain a "Do Not Sell or Share" opt-out mechanism
- Honor Global Privacy Control signals
- Process deletion requests within 45 days
- Keep records for 24 months

Penalties:
- $200/day for failure to register
- Civil penalties per CCPA: $2,500 unintentional, $7,500 intentional per violation
- CPPA can audit registrants proactively

## Gotchas
- Many ad-tech, data enrichment, and marketing analytics companies qualify as data brokers without realizing it
- Registration is a separate obligation from general CCPA compliance — non-registration is its own violation
- If you buy data from an unregistered data broker, that may expose you to additional liability
- The CPPA maintains a public registry — your customers and competitors can see if you are registered

## Related
- `ccpa-opt-out.md`
- `ccpa-privacy-policy-requirements.md`
