# plan-selection-free-team-enterprise

**Issue:** Picking a GitHub plan for a company is a licensing and security decision, not just a price tag. Free and Team orgs cannot do SAML SSO, SCIM provisioning, or audit log streaming at all; Advanced Security is not billed per seat but per *active committer* (a completely different unit); and some upgrades (Team to Enterprise Cloud) are one-click and in-place while others (anything involving Enterprise Managed Users) are a full migration with the GitHub Enterprise Importer. Teams that pick a plan by monthly sticker price routinely get trapped by a migration they did not know was required. This article is the decision matrix: what each plan costs, what each plan can and cannot do, which transitions are clean and which are one-way doors, and where the real cost levers are.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The plan ladder and what each tier actually buys

1. **GitHub Free (organization).** Zero cost, includes team access controls, 2,000 Actions minutes/month, 500 MB Packages storage, Dependabot alerts, and 2FA enforcement. Fine for a single-team open-source-adjacent org; has no SAML SSO, no required reviewers on private repos, and no audit log tooling worth the name.
2. **GitHub Team (~$4/user/month, first-year introductory rate).** Per-seat billing. Adds the collaboration controls that make private repos manageable: required and multiple PR reviewers, protected branches, code owners, scheduled reminders, insights graphs, security overview. Crucially, Team is the *smallest* plan that can buy the Code Security and Secret Protection add-ons for private repos.
3. **GitHub Enterprise Cloud (~$21/user/month, first-year introductory rate).** Everything in Team plus the identity and governance tier: SAML SSO, SCIM provisioning, audit log streaming, IP allow lists, enterprise accounts (multiple orgs under one owner), EMU option, internal repositories, rulesets, deployment protection rules, 50,000 Actions minutes/month, 99.9% uptime SLA, and Enterprise Support. If your security team asks for SSO or SIEM integration, you are buying this tier — there is no middle option.
4. **GitHub Enterprise Server.** Self-hosted, quoted via sales. Uses volume/subscription licensing for everything; GHAS on a standalone GHES instance is always a pre-purchased license pool, never metered. Chosen for data-residency or air-gapped requirements, not features — feature-wise GHEC is now ahead.
5. **GitHub Pro.** A personal-account plan, not an org plan. It shows up in pricing tables and confuses people; orgs skip it entirely.

## The security feature ladder (what locks you into Enterprise)

1. **SAML SSO + SCIM provisioning.** Enterprise Cloud only. This is the single most common forced upgrade: on Team, an offboarded employee's authorized tokens keep working until an owner manually removes them. See `github-saml-sso-enforcement.md` for the enforcement mechanics once you have the tier.
2. **Audit log streaming to SIEM.** Enterprise-only, enterprise-account-level feature. Team orgs are limited to API polling with 180-day retention. See `audit-log-streaming-siem.md`.
3. **Rulesets and internal repositories.** Enterprise includes organization/repository rulesets (the modern replacement for branch protection — see `github-rulesets-2026.md`) and internal repo visibility for cross-org sharing.
4. **Enterprise Managed Users (EMU).** Only exists on Enterprise Cloud. IdP-controlled accounts, no personal GitHub life outside the enterprise. Deep-dive in `github-enterprise-managed-users.md`.
5. **Advanced Security availability.** Code scanning / secret scanning are free on *public* repos on any plan. On private repos: Team can buy the Code Security and Secret Protection add-ons per-committer; the combined GHAS license is the Enterprise packaging. The *features* overlap heavily — the difference is licensing shape and volume discounts.

## Licensing model per plan: seats vs committers

1. **Platform seats are per-user, per-month.** Free/Team/Enterprise all bill the platform by unique billable users (members, outside collaborators on private repos, pending invites). Guest cleanup and dormant-seat reclamation are the levers here.
2. **Advanced Security bills per unique active committer — not per seat.** A committer is "active" if one of their commits was *pushed* to an enabled repo in the last 90 days, regardless of when it was authored. Bots (GitHub App identities) are ignored. One person committing to 40 enabled repos consumes exactly one license.
3. **Committer licenses are measured org-wide (or enterprise-wide).** Disabling a SKU on a repo frees the licenses of anyone who only commited there. This makes repo-level enablement the main GHAS cost control: enable Code Security on the 10 repos that matter, not the 400 that do not.
4. **Metered vs volume billing.** Enterprise Cloud supports metered billing (monthly invoice for actual active committers, no cap, supports hard budgets that block new enablements). Volume/subscription billing (annual pre-purchase, typical on GHES and enterprise agreements) blocks *new* enablements when exhausted but never disables already-enabled repos. Removing a user frees a volume license within ~24 hours.
5. **Migration amnesty.** Commits migrated via GitHub Enterprise Importer only consume licenses if pushed *after* migration — imported history does not bill. Verify current per-committer rates on github.com/security/plans (Code Security and Secret Protection are priced separately; a GHAS bundle covers both).

## Migration paths: clean upgrades vs one-way doors

1. **Free to Team, and Team to Enterprise Cloud: clean, in-place.** A plan upgrade on the same org keeps repos, issues, PRs, Actions, and members intact. Team to Enterprise Cloud also lets you *attach* the existing org to a new enterprise account without a data migration — identity, audit, and policy features then layer on top.
2. **Standalone org to EMU: migration required, no in-place conversion.** You cannot flip an existing org to Enterprise Managed Users. The documented path is GitHub Enterprise Importer (GEI) moving orgs into a new (or existing) enterprise — "source, history, and metadata" fidelity. Budget weeks, not days; community-reported timelines for large orgs run 12–26 weeks including planning.
3. **Between enterprises / adopting EMU on GitHub.com-to-GitHub.com: GEI.** Same tool, same fidelity tier. GHE.com to GitHub.com is *not* supported by official tools at all — that one goes through GitHub Expert Services.
4. **GHES to GHEC: GEI** (GHES 3.4.1+; Enterprise Live Migrations for 3.17+ to GHE.com). Fidelity is full source+history+metadata, but repos over ~40 GB fall back to source-and-history or Expert Services.
5. **From Bitbucket Cloud / plain Git / SVN / Mercurial: reduced scope.** Only source (and sometimes history) migrates with official tooling — issues and PRs do not. Plan metadata re-creation or third-party tooling before committing to these paths.

## Cost levers worth knowing before signing

1. **First-year introductory rates.** The published $4/$21 per-user monthly figures are introductory for the first 12 months; model renewal pricing with sales before year two.
2. **Base permission "none" + outside-collaborator roles.** Seats are consumed by anyone with access to private repos; granting read via team defaults rather than blanket membership keeps the seat count honest.
3. **GHAS repo-tiering.** Because committer billing is per enabled repo, a tiered rollout (crown jewels first) is the difference between licensing 50 committers and 2,000.
4. **Actions minutes and storage tiers scale with plan.** 2,000 (Free) / 3,000 (Team) / 50,000 (Enterprise Cloud) included minutes, and 500 MB / 2 GB / 50 GB Packages storage. Large-runner and GPU-runner costs are separate everywhere.
5. **Suspend instead of delete for temporary leavers.** Suspended/removed users free volume licenses quickly, but hard-deprovisioning an EMU user deletes their owned repos (see `scim-provisioning-lifecycle.md`) — "saving a license" and "keeping the data" are different decisions.

## Related

1. **`github-saml-sso-enforcement.md`.** The enforcement mechanics you unlock by buying Enterprise Cloud.
2. **`github-enterprise-managed-users.md`.** What EMU changes about identity, and why there is no in-place upgrade to it.
3. **`audit-log-streaming-siem.md`.** The enterprise-only streaming capability used to justify the tier to security.
4. **`corporate-org-setup-runbook.md`.** Ordered setup once the plan choice is made.
5. **`github-rulesets-2026.md`.** Rulesets availability follows the plan ladder.
