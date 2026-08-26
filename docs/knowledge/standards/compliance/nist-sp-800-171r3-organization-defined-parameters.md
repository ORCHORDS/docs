# NIST SP 800-171r3 organization-defined parameters

**Issue:** A control can appear implemented while its organization-defined parameter (ODP)—such as a timeout, notification period, or retention duration—is missing, inconsistent, or inherited without authorization.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Scope

NIST published final SP 800-171 Revision 3 and SP 800-171A Revision 3 in May 2024. Contractual applicability and CUI scope are agency/procurement determinations; this entry describes implementation governance, not legal advice.

## Controls

1. Inventory every ODP from the final publication and map it to affected systems.
2. Assign an authorized risk owner for each value and document rationale, dependencies, and source.
3. Store approved values in a versioned control catalog; reference them from implementation rather than duplicating prose.
4. Validate inherited provider values against the organization's requirement.
5. Encode machine-enforceable parameters in configuration and policy tests.
6. Route changes through impact analysis, approval, rollout, and evidence refresh.
7. Detect conflicting values across policy, configuration, contracts, and assessment plans.
8. Review parameters after risk, architecture, threat, or contractual changes.

## Verification

Sample an ODP from catalog through deployed configuration and SP 800-171A determination statement. Test boundary values. Confirm the assessor can identify who set the value and why. Fail assessment preparation on undefined placeholders.

## Gotchas

NIST defines the parameter slot, not the organization's risk decision. Copying another organization's value is not tailoring. Draft ODP lists must not be used against the final revision.

## Sources

- [NIST final SP 800-171r3 and 800-171Ar3 announcement](https://csrc.nist.gov/News/2024/updated-security-requirements-for-protecting-cui)
- [NIST SP 800-171 Revision 3 final](https://csrc.nist.gov/pubs/sp/800/171/r3/final)
