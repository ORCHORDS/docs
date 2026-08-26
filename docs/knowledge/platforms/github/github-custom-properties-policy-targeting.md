# GitHub custom properties for policy targeting

**Issue:** Organization-wide controls become either too broad or inconsistently hand-applied when repositories lack machine-readable ownership, sensitivity, lifecycle, and service-tier metadata.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use organization or enterprise custom properties as governed repository metadata, then target rulesets and automation from those properties. Keep the taxonomy small, documented, and non-sensitive because GitHub states that custom properties on public repositories are publicly visible.

## Property model

Useful controlled properties include:

- `service_tier`: critical, standard, experimental
- `data_class`: public, internal, restricted
- `lifecycle`: active, maintenance, archived
- `owner_team`: a stable team identifier
- `deploy_target`: none, edge, cloud, mobile

Prefer single-select values where drift would be costly. Define who may set each value, whether a value is required, and the default. Treat changes to critical values as auditable policy changes.

## Controls

1. Inventory repositories and map existing labels/topics to the proposed taxonomy.
2. Create properties centrally and require values where platform capabilities permit.
3. Apply rulesets using repository-property conditions, for example stronger review and signed-commit requirements for critical services.
4. Reconcile values through the REST API using a least-privilege GitHub App.
5. Alert on missing, invalid, or contradictory values.
6. Review property definitions before deleting or renaming them because policies and reports may depend on them.
7. Never store secrets, personal data, internal endpoints, or incident details in property values.

## Verification

- Query property values through the API and compare them with the authoritative service catalog.
- Use ruleset insights to confirm the expected repositories are matched.
- Test both inclusion and exclusion cases with non-production repositories.
- Change a test property and verify the intended policy selection changes without broadening unrelated access.
- Periodically sample ownership and lifecycle values against repository activity.

## Gotchas

- Metadata without an owner decays quickly.
- Free-form text creates spelling variants that break targeting.
- Public-repository properties are not a confidential inventory.
- A property-based ruleset still needs bypass governance and status-check design.

## Sources

- [GitHub Docs: Managing custom properties for organization repositories](https://docs.github.com/en/organizations/managing-organization-settings/managing-custom-properties-for-repositories-in-your-organization)
- [GitHub REST API: Repository custom properties](https://docs.github.com/en/rest/repos/custom-properties)
- [GitHub REST API: Rules and repository-property conditions](https://docs.github.com/en/rest/orgs/rules)
