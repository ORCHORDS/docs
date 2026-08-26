# environment-teardown-hygiene

**Issue:** Preview environments, per-PR stacks, test clusters, and one-off sandboxes can be created in minutes with IaC, but nothing enforces their destruction. Orphaned load balancers, idle compute, forgotten databases cloned from production, and stale secrets accumulate as zombie infrastructure — industry measurements repeatedly attribute 28-50 percent of cloud spend to waste, and abandoned environments are a top offender because they appear on no one's dashboard and belong to no current team. The cost is the smaller problem: stale environments run outdated dependencies, hold unrotated credentials, and expose lightly protected copies of real data, making them a preferred entry point for attackers. Teardown hygiene treats destruction as a first-class, planned part of the environment lifecycle — decided at creation time, executed automatically, and verified — rather than something someone remembers to do later.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Creation-time teardown contracts

1. **TTL stamped at birth.** Every ephemeral environment carries an expiry timestamp in its tags or metadata at creation, and a controller or scheduled job deprovisions anything past its TTL. The TTL is part of the create request, so an environment without one fails policy instead of living forever by default.

2. **PR-bound lifecycle.** Environments created for pull requests should be destroyed by the same automation that created them, triggered on merge and close events. The pull request is the natural unit of ownership; when it disappears from the board, its stack should disappear from the cloud account.

3. **Mandatory ownership tags.** Require owner, team, purpose, and expiry tags at provisioning time, enforced by policy (OPA/Kyverno, cloud tag policies, or CI checks) so untagged resources cannot be created. Tags are what make orphan detection and cost attribution possible later; retrofitting them never works.

4. **A named destroy path from day one.** The create pipeline must also own a tested destroy pipeline. If the environment was assembled with IaC, its destruction is a destroy job; if it was hand-assembled, it should not exist. Partial deletions that leave orphaned disks, NAT gateways, or DNS records are the primary source of zombie spend.

## Detection and inventory

1. **Scheduled garbage-collection scans.** Run nightly jobs that list environments older than N days, missing tags, or showing no activity (zero requests, no deploys, idle CPU) and act on them. Detection without action is reporting; pair every scan with the graduated enforcement below.

2. **A living registry of environments.** Maintain a single registry (even a simple database or JSON in git) mapping each environment to its creator, PR, creation date, TTL, and stack definition. When the registry and the cloud disagree, the cloud wins the audit and someone gets paged — that disagreement is exactly where zombies come from.

3. **Cost attribution per environment.** Route per-environment spend to the owning team via tags and show it on their dashboards. Waste that is invisible to the people who created it is never cleaned up; waste that shows up on a team's bill gets deleted within a sprint.

4. **Cloud-native idle detection.** Use provider tools (AWS Resource Explorer, Cost Explorer filters, Infracost, Cloud Custodian) to find low-activity and unattached resources that escape the environment abstraction entirely — unmounted volumes, unreferenced AMIs, orphaned snapshots. Case studies consistently show double-digit percentage storage savings from garbage-collecting these alone.

## Safe automated destruction

1. **Graduated enforcement.** Automated teardown should escalate: notify the owner a few days before expiry, suspend or scale-to-zero at expiry, then destroy after a grace period. Graduation protects against clock errors and genuinely-needed exceptions while keeping the default path fully automatic.

2. **Destroy through IaC, not console deletes.** Teardown must run the same tooling that created the stack (terraform destroy, pulumi destroy, helm uninstall, or the platform's environment API). Manual console deletions break state files and leave the half that the operator forgot, which is worse than no deletion because the inventory now lies.

3. **Deletion protection for shared state.** Anything a sandbox mounts from outside itself — shared databases, production-adjacent queues, shared buckets — gets deletion protection and a policy check that refuses to destroy resources outside the environment's own stack scope. The GC job should be unable to delete production even if misconfigured.

4. **Explicit data-handling rules.** Define at creation what happens to the data: test data is destroyed, production-derived data is scrubbed or destroyed per data policy, and nothing is retained "just in case" outside the retention rule. Abandoned environments holding stale copies of real data are a compliance incident waiting to be discovered.

## Organizational rules that make it stick

1. **Exceptions require renewal.** Long-lived environments are sometimes legitimate (a two-week QA soak). Allow them, but as explicitly registered exceptions with a human owner and a hard renewal date — the renewal is denied by default after two cycles, so exceptions expire without anyone volunteering to kill them.

2. **Teardown is part of done.** A feature or experiment is not complete until its temporary infrastructure is gone. Include environment removal in the definition of done and in PR templates, so reviewers ask "where does this stack get torn down?" at the same time they ask about tests.

3. **Audit the auditor.** Quarterly, reconcile actual cloud resources against the environment registry and billing. Measure zombie spend found and freed, and report it. What gets measured as recovered money keeps executive support for the automatic destruction of things people once cared about.
