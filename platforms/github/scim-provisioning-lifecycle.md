# scim-provisioning-lifecycle

**Issue:** SAML SSO without SCIM is half an identity solution: it proves who is logging in but never removes anyone. On a Team-Enterprise org with SAML only, an offboarded employee's authorized PATs and SSH keys keep working until an owner manually deletes the account on the GitHub side. SCIM closes the loop by letting the IdP (Entra ID, Okta, OneLogin) push lifecycle events to GitHub — but GitHub ships *two different SCIM implementations* (org-level for personal accounts, and enterprise-level for EMU), they must never be mixed, and the deprovisioning behavior differs sharply: org SCIM silently removes the member, EMU soft-deprovision suspends, and EMU hard-deprovision permanently deletes the user's owned repositories. Getting joiner/mover/leaver behavior wrong is how companies lose repos or strand ghost accounts. This article covers the full lifecycle: pairing rules, group-to-team mapping, and what actually happens to PRs, teams, and repos at each stage.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The two SCIM implementations and the SAML pairing rules

1. **Org-level SCIM (personal accounts on GitHub.com).** Requires SAML SSO *enforced first* — which itself requires Enterprise Cloud. It manages membership of one organization via a third-party OAuth app; it cannot be used with an enterprise account or managed users. Supported IdPs: Entra ID, Okta, OneLogin.
2. **Enterprise SCIM for EMU.** A separate implementation that provisions managed-user accounts into the enterprise (see `github-enterprise-managed-users.md`). IdPs: Entra ID, Okta, PingFederate. Never mix the two — an org-level SCIM app pointed at an EMU enterprise will produce unlinkable identities.
3. **NameID/userName must match exactly.** SCIM links a SAML identity to a provisioned SCIM identity by matching the SAML `NameID` with the SCIM `userName` per user. Any mismatch provisions an account that can never complete SSO login.
4. **Org SCIM runs through a dedicated OAuth app authorized by one specific user.** If that authorizing user leaves, SCIM breaks. GitHub's guidance: authorize via a dedicated bot account that is an organization owner — it consumes one license but never leaves.
5. **SAML alone leaves orphans.** Without SCIM, removing a user from the IdP does nothing on GitHub: expired SSO sessions still leave working authorized tokens, PATs re-authorized via SSO, and SSH keys. Removal must be done manually in both systems, which is exactly what SCIM automates.

## Provisioning (joiner) and group-to-team mapping

1. **IdP is the source of truth.** Once SCIM is on, every membership change should originate in the IdP. Manual invites on GitHub create members that are not linked to a SCIM identity — and an unlinked member can never be deprovisioned by SCIM later.
2. **One IdP group maps to one team — but a group can map to many teams.** A GitHub team can connect to exactly one IdP group; the same IdP group can feed multiple teams. Once connected, membership must be changed in the IdP, not on GitHub.
3. **Clear manual members before linking.** You must remove manually-added members before connecting an existing team to an IdP group; afterwards direct membership management on GitHub is not possible. Synced teams also cannot be parent/child teams, and members of IdP-managed teams cannot hold the team maintainer role.
4. **Entra ID: security groups only.** Nested groups and Microsoft 365 groups are not supported — a nested membership structure silently fails to propagate.
5. **Daily reconciliation, plus event-driven sync.** GitHub runs a daily reconciliation job against stored IdP group data, and re-syncs whenever a Group SCIM API call lands or an admin links/unlinks a team. If a change pulls a user into a team whose org they were not in, GitHub adds them to the org automatically. Failures log `external_group.scim_api_failure` audit events; watch for those.
6. **Repo access stays on GitHub.** SCIM manages *team membership*; which repos a team can read is still configured on the GitHub side. Provisioning therefore does not grant repo access by itself.

## Deprovisioning (leaver) — org-level SCIM behavior

1. **Removal from the org is automatic and immediate.** A SCIM deprovision removes the member from the organization. Their open PRs and issues remain (comments and commits keep the author attribution); the org loses nothing they created in org-owned repos.
2. **Team memberships vanish via reconciliation.** The user is dropped from every SCIM-mapped team; if they were only in the org through those teams, org membership goes with it.
3. **Forks and personal content are not the org's problem.** Org SCIM deprovision removes org membership — the user's personal account, personal repos, and forks under their own namespace survive untouched (they just lose access to the org's private repos).
4. **Manual removal leaves a stale linked identity.** If an owner removes the member in the GitHub UI instead of the IdP, the SCIM link goes stale and can break a future rejoin. Correct leaver flow: disable in the IdP, let SCIM remove, then verify.

## Deprovisioning (leaver) — EMU soft vs hard, and what dies

1. **Soft-deprovision (SCIM `active: false`, i.e. PUT/PATCH).** The account is suspended, never deleted. Username/email are obfuscated, SCIM identity stays linked, and the user is dropped from SCIM-mapped teams and IdP-managed orgs. Forks of private/internal repos are deleted within 24 hours — but restored if the user is unsuspended within 90 days. Audit log shows `user.suspend`.
2. **Hard-deprovision (SCIM DELETE).** Unrecoverable. Linked SCIM identity, PATs (classic and fine-grained), SSH keys, GPG keys, and app authorizations are all deleted — breaking commit signature verification on anything keyed to them — and repositories *owned by the user are deleted*. Comments/issues/PRs they authored in enterprise repos are retained, but permanently detached from a usable account.
3. **IdP defaults matter.** Okta never sends hard-deprovision calls (its "Suspend" button sends nothing to GitHub at all — only "Deactivate" soft-deprovisions). Entra ID auto-escalates: soft-deleted users are hard-deleted after 30 days, which means an Entra org that waits a month loses those users' owned repos permanently.
4. **Reinstatement only works with the same IdP account.** A soft-deprovisioned user can be reactivated (Entra: reassign to the app or "Provision on Demand", ~40 minutes; Okta: reactivate/reassign; REST: `PATCH /scim/v2/enterprises/{enterprise}/Users/{id}` with `active: true`). The SCIM external ID linkage cannot be retargeted to a different IdP account.
5. **Reprovisioning after hard-delete means a new account.** A new account can reuse the username and, with a matching email, Git will attribute new commits to it — but it never merges with the old account's history.

## Mover edge cases

1. **Team moves are group changes.** A mover between teams is an IdP group swap; reconciliation adds them to the new team's org if needed and drops them from the old team. Done in the IdP, this needs no GitHub-side work.
2. **Removing a user from *one* mapped group ≠ removing them from the org.** Users added via IdP groups must be removed from *all* mapped groups for that org before org membership drops; users added manually must be removed manually — unassigning the EMU application in the IdP only suspends them.
3. **Disconnecting a group from a team removes the members it brought in.** Users who joined the org *only* via that team-membership are removed when the link is severed; members who had other membership paths stay.
4. **Watch the audit log for SCIM health.** `external_group.scim_api_success/failure` (group sync), `user.suspend`/`user.unsuspend` (EMU lifecycle), and org member add/remove events give you a full lifecycle trail — streamable per `audit-log-streaming-siem.md`.

## Related

1. **`github-saml-sso-enforcement.md`.** SAML is the prerequisite layer; enforce it before SCIM.
2. **`github-enterprise-managed-users.md`.** EMU account model that the enterprise SCIM implementation provisions.
3. **`plan-selection-free-team-enterprise.md`.** Why SCIM requires Enterprise Cloud (and what Team orgs must do manually instead).
4. **`audit-log-streaming-siem.md`.** Alerting on `user.suspend` and SCIM failure events.
5. **`corporate-org-setup-runbook.md`.** Ordering: SAML enforce, then SCIM, then group-to-team mapping.
