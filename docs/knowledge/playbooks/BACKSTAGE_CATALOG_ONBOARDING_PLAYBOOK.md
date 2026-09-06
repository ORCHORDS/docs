# Backstage Catalog Onboarding Playbook

## Purpose

Onboard a service, library, or resource into the Backstage software catalog under the version, plugin, and identity constraints in `BACKSTAGE_VERSION_GOVERNANCE.md` without breaking the portal, the scaffolder, or TechDocs.

## Audience

Platform engineers, developer experience (DevEx) engineers, service owners, and TechDocs authors.

## Pre-conditions

- The Backstage deployment runs a supported release under `BACKSTAGE_VERSION_GOVERNANCE.md`.
- The catalog entities registered file (`catalog-info.yaml`) schema is documented and version-controlled.
- The scaffolder backend and TechDocs publisher and reader are pinned to versions that match the running core minor.
- Identity provider (GitHub Apps, GitLab, Okta, or Google IAP) is configured and reachable.

## Procedure

### Step 1 — Draft the catalog entry

1. Copy the entity template from the documented catalog template.
2. Fill in the entity name, description, owner, system, and tags.
3. Reference dependencies and links (source repo, CI, on-call rotation, runbook).
4. Validate the YAML against the catalog schema before commit.

### Step 2 — Register the source

5. Place `catalog-info.yaml` at the repository root, in a `docs/` subfolder, or in the documented `catalog/` folder.
6. Configure the source integration (GitHub, GitLab, Bitbucket, or Azure DevOps) to discover the file.
7. Verify the integration token has read access to the repo and the discovered file is reachable.

### Step 3 — Validate the entry

8. Trigger an on-demand catalog refresh.
9. Verify the entity appears in the catalog UI.
10. Verify the links resolve (source, CI, runbook, on-call rotation).
11. Verify the owner team resolves to a real group in the identity provider.

### Step 4 — Wire TechDocs

12. Verify the TechDocs publisher is configured for the source.
13. Trigger a TechDocs build and confirm the site renders.
14. Pin the mkdocs.yml overrides and review them under change control.

### Step 5 — Wire scaffolder (optional)

15. If the entity will be created via a software template, verify the template action set matches the running core minor.
16. Run the template in dry-run mode and confirm the produced tree matches expectations.

### Step 6 — Verify and operate

17. Confirm the entity is visible in the catalog UI and searchable.
18. Confirm the TechDocs site renders and is reachable.
19. Capture a recent catalog refresh log and the most recent TechDocs build evidence.

## Rollback

- Remove the entity from `catalog-info.yaml` and revert the source change.
- Remove the entity via the catalog API if the file deletion does not propagate.
- Capture the failure mode and update the catalog template if the failure was schema-related.

References: `BACKSTAGE_VERSION_GOVERNANCE.md`, `KYVERNO_POLICY_ROLLOUT_PLAYBOOK.md`, `FLUX_HELM_RELEASE_UPGRADE_PLAYBOOK.md`.
