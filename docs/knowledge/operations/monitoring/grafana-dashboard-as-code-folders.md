# Grafana Dashboard-as-Code Folder Permissions

Dashboards that live only in the UI die with the person who made them. Grafana's provisioning system solves the lifecycle half of that problem — YAML files in a watched directory create and update data sources, dashboards, and alert rules on startup — but the folder layer is where as-code deployments usually leak: folders created ad hoc in the UI, permissions granted by hand, and provisioned dashboards landing in a folder whose access rules nobody reviewed. Getting folder permissions into the same version-controlled workflow as the dashboards themselves is the subject of this article.

## Scope

Covers Grafana's dashboard-as-code mechanics with a focus on folders: provisioning YAML for dashboards and folder assignment, the separate folder provisioning API (folders are not fully expressible in the same provisioning block in all versions), permission models (roles, teams, and users granted at folder level, inherited by contained dashboards), and how provisioned resources interact with UI edits. Applies to self-hosted Grafana with the provisioning directory. Excludes Grafana's newer GitSync workflow and Kubernetes operator approaches except as noted alternatives, and excludes plugin and alert-rule provisioning beyond their folder interaction.

## Workflow or implementation guidance

Build the folder hierarchy as deliberately as the dashboards.

1. Design the folder hierarchy around access boundaries, not aesthetics. Folder permissions cascade to the dashboards inside, so folders should correspond to the teams who own and view those dashboards: an operations folder, a payments folder, a platform folder. A hierarchy organized by dashboard type (all "latency" dashboards together) fights the permission model, because viewership cuts across it.
2. Provision dashboards with explicit folder targeting. In the dashboard provisioning YAML, each entry specifies the folder by name or ID (folder names are resolved by Grafana; the folder must exist or be creatable per the provisioning options). Set `allowUiUpdates` deliberately: with updates disallowed, UI edits to provisioned dashboards are blocked, which is the safe posture for source-of-truth dashboards; with updates allowed, the UI can diverge from the repository and the next provisioning cycle overwrites the changes — a documented, expected loss, not a bug.
3. Create and manage folders through a repeatable mechanism. Depending on Grafana version, folders can be provisioned via dedicated provisioning support or created through the HTTP API in your deployment pipeline. Whichever mechanism you use, it must be idempotent and run before dashboard provisioning, because dashboard provisioning resolves folder names at load time. Record the folder list in the repository alongside the dashboards so the hierarchy is reviewable in diffs.
4. Apply permissions at the folder, not per dashboard. Grant the minimum: the owning team gets edit, broader viewer groups get view, and anything sensitive stays unshared or restricted to a named team. Per-dashboard permission exceptions create an unauditable lattice; folder-level grants keep the permission story one list per folder. Manage these grants through the API in the same pipeline step that ensures folders, so permissions are reviewable as code too.
5. Handle the special folders correctly. The general folder (the root of the dashboard tree) and any pre-seeded folders have their own semantics; do not build the hierarchy beneath a folder whose deletion would cascade. Library panels and their containing folders also interact with provisioning, so if dashboards reference shared panels, provision those as well.
6. Validate end to end after deployment: a fresh Grafana instance pointed at the provisioning directory must come up with the full hierarchy, dashboards in the right folders, and permissions intact. That cold-start reproducibility is the real test of as-code status.

## Controls

- Provisioning directory in version control, with a CI step validating YAML syntax and dashboard JSON models before merge.
- Folder inventory in the repository with an owner annotation per folder; CI diff review covers folder additions and removals.
- Permission grants applied only by the pipeline's API step; direct UI permission changes audited (via Grafana's audit logging where enabled) and reverted.
- `allowUiUpdates` set to false for all source-of-truth dashboards, with any exception documented in the provisioning file comments.
- Cold-start test in CI or staging: a clean Grafana instance with the provisioning directory must reproduce the full dashboard, folder, and permission state, compared against a recorded manifest.
- Quarterly access review exporting folder permissions and reconciling against team membership.

## Validation evidence

The cold-start manifest is the central artifact: the exported list of folders, dashboards-per-folder, and permission grants from a freshly provisioned instance, diffed against the repository's declared state — a clean diff proves the code fully describes the system. Supporting artifacts: provisioning log output from a real restart showing dashboards placed (not duplicated) into the correct folders, and an access check matrix showing a viewer-team account sees exactly its folders and no others, executed with test credentials after each permission change.

## Failure modes and correction

- Dashboards land in the general folder despite config: the target folder did not exist at provisioning time (creation ordering) or the name has a typo or trailing space. Fix ordering — ensure folders before dashboards — and validate names in CI.
- Duplicate dashboards after renames: provisioning keys on the file path, so renaming a JSON file creates a new dashboard rather than moving the old one. Perform renames as a two-step (add new, remove old) or use the update path the version supports.
- UI edits vanish overnight: `allowUiUpdates` false overwrote them, exactly as designed. Route the change through the repository; communicate the overwrite rule at onboarding.
- Permissions missing after restore or migration: grants applied by pipeline to the old instance were never captured in code. Re-run the permission step and reconcile the export.
- Folder deletion cascades dashboards unexpectedly: folders own their contained dashboards. Add a CI check that no provisioning entry targets a folder marked deprecated without an explicit migration plan.
- Teams referenced before they exist: folder grants naming a team that the pipeline has not yet created fail silently in some versions. Order the pipeline: teams, folders, permissions, dashboards.

## Limitations

Provisioning capabilities differ meaningfully across Grafana versions — notably whether folders themselves are provisionable via YAML, how `allowUiUpdates` behaves, and how folder IDs resolve — so the running version's documentation is authoritative and migrations require revalidation. The HTTP API route for folders and permissions requires administrative credentials in the pipeline, which must be secret-managed. Grafana's audit logging and permission export coverage vary by edition. The newer GitSync feature and Grafana's Kubernetes operator offer overlapping functionality with different trade-offs not evaluated here. Finally, folder permission inheritance covers dashboards, not alert rules in all versions; rule-folder permissions have their own semantics.

## Canonical sources

- Grafana provisioning documentation: https://grafana.com/docs/grafana/latest/administration/provisioning/
- Grafana folder HTTP API: https://grafana.com/docs/grafana/latest/developers/http_api/folder/
