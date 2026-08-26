# GitHub required-status-check source-app binding

**Issue:** Any person or integration with repository write permission can set a commit status. Requiring only a status-check name can therefore accept a result from an unintended producer unless the ruleset binds that required check to the expected GitHub App.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- For each required status context, select the expected source App rather than `any source` when the trusted producer is a GitHub App.
- Install the App only on required repositories and grant `statuses:write` plus the minimum other permissions it needs.
- Establish the check first: GitHub requires a pre-existing required status check associated with an App that has recently submitted a check run before the App can be selected.
- Keep required context names stable and unique across trust domains; avoid letting a low-trust workflow reuse a high-trust check name.
- Inventory classic commit statuses and Checks API results, their Apps, token owners, workflow files, and reusable-workflow callers.
- Protect the workflow and configuration that produce the check with CODEOWNERS, required review, immutable action references, and least-privileged tokens.
- Alert on a required context emitted by an unexpected actor or App even when GitHub blocks the merge.
- Maintain a staged cutover and rollback procedure for App replacement or installation transfer.

## Implementation and tests

Create a sandbox ruleset with a required check and select the intended App as expected source. Submit a success from that App and verify merge can proceed. Then submit the same context name and success state from a personal token or another integration; verify merge remains blocked.

Test App uninstall, missing `statuses:write`, expired installation token, renamed context, no recent check run, duplicate Checks and Statuses names, fork pull request, merge queue, and App migration. Inspect the merge box and API output to confirm the accepted result’s source.

## Gotchas and applicability

Selecting `any source` leaves manual source inspection to reviewers. Source binding authenticates who supplied the result; it does not prove the workflow tested the right commit, used safe code, or resisted a compromised App. Strict versus loose up-to-date policy is a separate decision.

For organization-level status-check rules, verify App installation and permission visibility in the organization context.

## Official sources

- [GitHub Docs: Available rules for rulesets—required status checks](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets#require-status-checks-to-pass-before-merging)
- [GitHub Docs: Status checks](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/collaborating-on-repositories-with-code-quality-features/troubleshooting-required-status-checks)
