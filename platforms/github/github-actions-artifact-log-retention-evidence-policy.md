# GitHub Actions artifact and log retention as an evidence policy

**Issue:** CI artifacts and logs are often kept at the platform default without asking whether that preserves required release evidence or retains sensitive debug material too long. GitHub retention settings affect new objects only, so a policy change without an inventory leaves historical risk and evidence gaps unchanged.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Set retention by evidence class

1. **Classify before assigning days.** Separate disposable build output, test reports, release provenance, security findings, and operational logs. Retention should follow a legal, security, or recovery purpose—not storage convenience.
2. **Use the narrowest adequate period.** GitHub documents a default 90-day artifact/log retention. Public repositories allow 1–90 days; private/internal repositories allow 1–400 days, subject to organization or enterprise limits.
3. **Do not put secrets in artifacts or logs.** Retention does not make an exposed credential safe. Redact before upload, scope access, and use a secret manager for sensitive material.
4. **Set an organization ceiling and repository exceptions.** Central maximums prevent a forgotten repository from retaining logs indefinitely; exceptions should name the evidence purpose, owner, and review date.
5. **Record the effective configuration.** Managed-repository and organization limits can override a repository choice, so evidence owners need the resolved setting, not merely workflow YAML.

## Change procedure

1. Inventory current artifacts and logs, their audience, and the business reason to retain them.
2. Choose organization defaults and maximums; set a per-artifact retention-days value only where an exception is justified.
3. Apply the change and document its effective date: GitHub applies retention changes only to newly created artifacts and logs.
4. Handle historical objects separately under the approved preservation/deletion process.
5. Verify a test workflow’s expiration and access controls; repeat after organization-policy changes.

## Failure modes

- **Assuming a new policy changes old artifacts:** it does not.
- **Keeping logs “for debugging” without an owner:** debug logs can contain identifiers, request bodies, and operational details.
- **Deleting release evidence with routine build output:** provenance, signed deliverables, and validation records often have different retention needs.
- **Treating cache retention as artifact retention:** they are separate controls with different eviction and cost behavior.

## Sources

- [GitHub Docs: configuring organization artifact and log retention](https://docs.github.com/en/organizations/managing-organization-settings/configuring-the-retention-period-for-github-actions-artifacts-and-logs-in-your-organization)
- [GitHub Docs: managing Actions settings for a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository)
