# GitHub custom repository-role permission layering

**Issue:** A custom repository role is an inherited standard role plus additional permissions; it cannot subtract permissions. Because organization base permission, teams, direct grants, and roles are additive, a narrowly named custom role can still produce broad effective access.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Confirm the organization uses GitHub Enterprise Cloud, which is required to create custom repository roles.
- Select the lowest viable inherited role—Read, Triage, Write, or Maintain—then add only individually justified permissions.
- Keep dangerous additions such as bypass branch protections, edit repository rules, manage Actions, runners, secrets, environments, webhooks, deploy keys, or protected refs in separately approved roles.
- Calculate effective access across organization base permissions, team nesting and membership, direct repository grants, custom roles, outside-collaborator access, and ownership.
- Record role name, purpose, inherited role, added permissions, owner, approver, assignees, repository scope, review date, and removal plan.
- Review GitHub’s “Mixed roles” warning and audit role assignments after team or base-permission changes.
- Test access with a non-owner account; owners and bypass actors are not representative least-privilege subjects.

## Implementation and tests

Create a permission matrix of required actions and forbidden actions, then exercise both through the UI, Git transport, REST API, GraphQL API, Actions, and branch protection. Verify that a user can perform each intended operation and is denied every destructive or governance operation outside scope.

Before editing or deleting a role, export assignments and model the resulting access. GitHub documents that deleting a custom role reassigns users, teams, and pending invitations to the organization’s base permissions; verify that fallback before approval and retest afterward.

## Gotchas and applicability

GitHub allows up to 20 custom repository roles on Enterprise Cloud. Additional permissions only add to the inherited role, and multiple access paths sum rather than cancel each other. A custom role for specific repositories is different from a custom organization role that can apply across organization resources.

Feature availability and permission names can change by plan and GitHub product; verify current documentation and the target organization.

## Official sources

- [GitHub Docs: About custom repository roles](https://docs.github.com/en/enterprise-cloud@latest/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/about-custom-repository-roles)
- [GitHub Docs: Managing custom repository roles](https://docs.github.com/en/enterprise-cloud@latest/organizations/managing-user-access-to-your-organizations-repositories/managing-repository-roles/managing-custom-repository-roles-for-an-organization)
