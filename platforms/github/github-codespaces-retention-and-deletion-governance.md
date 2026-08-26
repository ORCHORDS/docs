# Set Codespaces Retention and Deletion Governance

**Issue:** Stopped codespaces retain storage, source, local changes, credentials, and forwarded configuration until deletion. Unlimited or inconsistent retention increases cost and data exposure.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls
- Set organization retention and idle-timeout policies by repository risk and workflow need.
- Distinguish idle stopping from deletion and communicate both to users.
- Require durable work to be committed or exported before deletion deadlines.
- Inventory organization-paid codespaces, owners, last use, size, repository, and policy exception.
- Revoke access and delete codespaces promptly during offboarding or repository access removal.
- Review secrets and tokens for expiration independent of codespace deletion.

## Verification
- Create, stop, age, and delete test codespaces under policy and verify timing.
- Offboard a test identity and confirm codespaces and access are removed.
- Restore work only through documented source/artifact paths, not assumed local persistence.
- Reconcile billing inventory with policy exceptions.

## Gotchas
Stopping saves compute but storage continues. Deleting a codespace can destroy unpushed local work; retention is not backup.

## Official sources
- [GitHub: Restricting retention periods](https://docs.github.com/en/codespaces/managing-codespaces-for-your-organization/restricting-the-retention-period-for-codespaces)
- [GitHub: Restricting idle timeout](https://docs.github.com/en/codespaces/managing-codespaces-for-your-organization/restricting-the-idle-timeout-period)
