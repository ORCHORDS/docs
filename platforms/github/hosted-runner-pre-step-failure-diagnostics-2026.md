# hosted-runner-pre-step-failure-diagnostics-2026

**Issue:** A GitHub Actions job targeting a standard GitHub-hosted runner fails before step 1 starts, often across multiple valid runner labels, while equivalent self-hosted jobs still run. This pattern is easy to misdiagnose as application, workflow-step, Node, package-manager, or image-specific breakage even though no repository code has executed yet.

**Date:** 2026-08-19
**Author:** ORCHORDS
**Status:** verified-live

## Symptom

Typical evidence:

- the workflow run is created normally;
- each affected job reaches `completed/failure` almost immediately;
- the job API contains no executed steps, or `steps` is empty/null;
- changing from one documented standard image (for example `ubuntu-24.04`) to another valid image (for example `ubuntu-22.04`) produces the same pre-step failure;
- a self-hosted runner workflow in the same private repository still schedules and executes normal checkout/setup/build steps.

That combination means **application and test code have not run yet**. Treat the problem as runner admission/provisioning/account policy until evidence says otherwise.

## Primary causes to investigate

1. **Standard GitHub-hosted runners disabled by organization or enterprise policy.** GitHub lets organization/enterprise owners disable standard hosted runners so workflows must use permitted runner groups instead.
2. **Actions billing/budget restrictions for a private repository.** Private repositories consume the account/organization's GitHub-hosted Actions minutes and may be blocked when spending/budget policy does not permit more hosted usage.
3. **Runner-group or enterprise policy restrictions.** Enterprise policy can constrain which organizations/repositories may use runner groups or standard hosted runners.
4. **Image-label problem.** Consider this only after testing another currently documented label. If two valid standard labels fail identically before step 1, image-specific incompatibility becomes unlikely.

## Diagnostic sequence

1. **Inspect the job object, not application logs first.** If there are no job steps, do not debug TypeScript, pnpm, checkout, environment variables, test commands, or application code yet.
2. **Confirm the runner label is current and supported** in GitHub's hosted-runner reference.
3. **Try one other pinned supported standard image** on an isolated draft branch. Do not repeatedly churn labels.
4. **Compare with a known self-hosted job** in the same repository. If self-hosted executes while multiple hosted images fail before step 1, move investigation to organization/enterprise Actions settings and billing.
5. **Check organization/enterprise policy:** Actions → General → Standard hosted runners. Verify they are not disabled for the repository's policy scope.
6. **Check Actions billing/budget** for the repository owner/organization. Private-repository hosted minutes are charged to the repository owner.
7. **Keep production workflows unchanged** while diagnosing. Use a draft PR or disposable branch so a failed hosted-runner experiment cannot break deploy gates.
8. **Document the exact boundary:** "runner did not provision / no steps ran" is materially different from "CI tests failed."

## Safe migration pattern from persistent self-hosted CI

When ordinary secretless PR validation is unnecessarily serialized on one long-lived self-hosted machine:

- create a dedicated infrastructure issue;
- change only the ordinary CI `runs-on` target in a draft PR;
- preserve job/check names, workflow permissions, commands, timeouts, concurrency semantics, and deployment gates;
- leave deployment/release workflows and credentials untouched;
- require the migration PR to prove that hosted jobs actually start and pass before merging;
- if hosted jobs fail before step 1, keep the migration draft blocked and leave the working self-hosted configuration on the default branch.

This prevents a well-intentioned capacity/security change from disabling all required CI.

## What not to do

- Do not modify application code to fix a job that never reached checkout.
- Do not weaken required checks or merge around the failure.
- Do not assume `ubuntu-latest` will solve an account policy/billing block.
- Do not switch production deployment jobs away from a trusted runner boundary merely to test standard hosted-runner availability.
- Do not claim an image incompatibility solely because one hosted label failed before any step.
- Do not expose billing identifiers, runner registration tokens, organization secrets, or repository credentials in diagnostics.

## Verification

A hosted-runner migration is verified only when:

- the job reports a documented hosted runner image;
- `Set up job` and checkout/setup steps actually execute;
- the unchanged CI commands pass;
- required check names remain compatible with branch/deployment gates;
- no new secret is made available to pull-request code;
- deployment/release jobs retain their intended protected runner/environment boundary.

## Sources

- GitHub-hosted runners reference: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- Organization Actions policy / disabling standard hosted runners: https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization
- Runner groups: https://docs.github.com/en/actions/concepts/runners/runner-groups

## Related

- `corporate-org-setup-runbook.md`
- self-hosted runner hardening and runner-group entries
- CI contract-drift / readiness-gate entries
