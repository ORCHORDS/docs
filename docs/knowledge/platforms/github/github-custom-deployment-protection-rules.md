# github-custom-deployment-protection-rules

**Issue:** GitHub environments ship with built-in protection: required reviewers, wait timers, branch restrictions, and deployment branch policies. But real organizations gate deploys on conditions GitHub knows nothing about — a change ticket must be approved in ServiceNow, a canary analysis in Datadog or Honeycomb must be green, a maintenance window must be open, an on-call sign-off must exist in the incident tool. Teams historically faked this with a manual approval step that a human performed after checking the external system, which drifts and audits poorly. Custom deployment protection rules close the gap properly: a GitHub App, installed on the repository and enabled per environment, becomes an additional required gate that a workflow job referencing that environment must pass before the deployment proceeds. The job pauses, the app evaluates the external condition via webhook, and the workflow only continues when the app responds with success.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## How the mechanism works

1. **A GitHub App becomes the rule.** Deployment protection rules are implemented as GitHub Apps. You either install a partner app (Datadog, Honeycomb, New Relic, NCM NodeSource, and ServiceNow all ship official implementations) or build an internal app that receives the `deployment_protection_rule` webhook and decides approve/reject.
2. **Enable per environment, not per repo.** After the app is installed, Settings → Environments → select environment → check the rule under Deployment protection rules → Save protection rules. The gate applies only where enabled, so staging can stay un-gated while production requires it.
3. **The job waits for the app's verdict.** When a workflow reaches a job that references the environment, the rule fires and waits for the app's response — up to 30 days before the job times out and fails. The verdict is delivered through the API (the deployment protection rule endpoints on the workflow run), not by editing the workflow file, so the gate is enforced server-side.
4. **Up to six rules per environment.** Any number of rule apps can be installed on a repository, but a maximum of 6 deployment protection rules can be enabled on any single environment at once. All enabled rules must pass; one rejection fails the gate.

## Designing an internal rule app

1. **Subscribe to the right webhook.** The app listens for the deployment protection rule event triggered when a job referencing the protected environment starts. The payload identifies the environment, the run, and the callback targets your app needs to approve or reject.
2. **Respond asynchronously, evaluate externally.** The app should acknowledge the webhook, run its real check (query ServiceNow, poll canary metrics, check the calendar), then call back with the decision. Do not try to inline a multi-minute analysis in the webhook handler — the 30-day window exists precisely for slow human-speed processes like ticket approval.
3. **Fail closed with a timeout policy.** Decide what happens when the external system is down or the app itself errors: reject (safe, blocks deploys during tooling outages) or approve (fast, but silently disables the gate). The conservative default for production environments is fail closed with clear error annotations in the run.
4. **Audit every decision.** Record which rule instance approved or rejected which run, with the external evidence (ticket ID, metric window). Approval outcomes are visible in the deployment details in the GitHub UI, so the app's decisions must line up with what your auditors see there.
5. **Version the rule logic outside the gate.** Ship rule changes as normal app releases with changelogs; a silently changed gate policy is a production risk of the same order as a silently changed deploy pipeline.

## Combining rules with the rest of the gate stack

1. **Layer with required reviewers.** Built-in required reviewers and custom rules compose: reviewers answer "should a human allow this," rules answer "are the external conditions met." Enabling both means an approved reviewer still cannot deploy into a closed maintenance window.
2. **Use branch policies to scope the rule's blast radius.** Deployment branch and tag policies restrict which refs can deploy to the environment at all; the custom rule then only evaluates the smaller set. This keeps the external system calls (and their cost) bounded.
3. **Pair with rulesets for who can deploy.** Repository rulesets control who can push/merge to the deploying branch; the environment rules control whether the deploy runs. Treat them as separate questions — identity from rulesets, conditions from deployment protection.
4. **Put the gate before the spend.** Order the environment's protections so cheap checks (wait timer, branch policy) run before expensive ones (external API calls), because every enabled protection must pass anyway.

## Operational pitfalls

1. **The 30-day wait is not a queue.** A forgotten blocked deployment sits in waiting state for up to a month; alert on deployments waiting longer than your real policy window so stale gates surface as failures instead of zombies.
2. **App permission drift breaks gates silently.** If the rule app is uninstalled or loses repository access, protection behavior becomes undefined from the workflow's perspective — monitor app installation as part of environment config, and re-verify after org-level app policy changes.
3. **Six-rule ceiling forces design choices.** Teams that want eight gates must consolidate (one meta-rule app that checks multiple systems), which is usually a feature: it forces the approval logic into one auditable place.
4. **Partner rules first, custom second.** Before building an internal app for a system a partner already covers, evaluate the official implementation — maintaining a ServiceNow integration is not a differentiated engineering investment for most orgs.
