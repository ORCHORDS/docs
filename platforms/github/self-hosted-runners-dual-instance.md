# self-hosted-runners-dual-instance

**Issue:** A single Linux machine needs to serve GitHub Actions jobs for two different GitHub organizations — for us, driven by CI-minutes exhaustion: both orgs burned through their Actions free/included-minute budgets, and moving every job to hardware we already owned reduced the Actions bill to zero (usage is free for self-hosted runners). The catch is that a runner registration is bound to exactly one org (or repo, or enterprise) — it cannot be shared across two orgs — so the machine must run two independent runner instances, each registered to a different org, managed as separate systemd services without the two colliding on ports, work directories, or users. This article is the dual-instance setup, the routing mechanics (runner groups, labels), and the security trade-off you accept the moment self-hosted runners meet public repos.

**Date:** 2026-08-15
**Repo:** ORCHORDS (workflow, multi-repo)
**Author:** ORCHORDS
**Status:** published

## Why two instances: one registration, one org

1. **A runner registration token scopes the runner to a single target.** `config.sh` registers against exactly one org, repo, or enterprise; GitHub's own community answers confirm a single registration cannot serve two organizations. The only single-registration multi-org construct is enterprise-level runners on GitHub Enterprise Cloud — irrelevant for two independent orgs on ordinary plans.
2. **Therefore: two runner directories, two runner names, two services.** Each instance is a full, unmodified runner install in its own directory (e.g., `/opt/runner-orgA` and `/opt/runner-orgB`), configured from that org's Settings > Actions > Runners > New self-hosted runner command, with a unique `--name` (e.g., `ci-box-orgA`, `ci-box-orgB`) and its own work directory. Same machine, same kernel, same disk — isolated directory trees.
3. **Cost model: self-hosted minutes are free.** GitHub's billing docs state Actions usage is free for self-hosted runners (and for public repositories) — self-hosted jobs consume zero included minutes, on any plan. This is the entire economic argument for the setup; verify current terms in `github/ci-budget-exhaustion-migration.md` before relying on it at scale.

## Setup: two directories, two names, two systemd services

1. **Configure each instance in its own directory.** As the intended service user: `cd /opt/runner-orgA && ./config.sh --url https://github.com/orgA --token <orgA-token> --name ci-box-orgA --labels orgA,linux,self-hosted`. Repeat in `/opt/runner-orgB` with orgB's token, name, and labels. Never reuse a directory, a name, or a registration token across orgs.
2. **`svc.sh install` creates one service per instance.** Each directory's `./svc.sh install && ./svc.sh start` produces an independent systemd unit named after the org and runner name — `actions.runner.orgA-ci-box-orgA.service` and `actions.runner.orgB-ci-box-orgB.service` — which start at boot independently, restart independently, and can be upgraded one at a time with near-zero CI downtime (drain one org's runner, patch it, bring it back, then the other).
3. **Run each service as a different Linux user.** Create `runner-orgA` and `runner-orgB` system accounts and install each service under its own account. Because jobs execute with the service user's privileges, per-org users are the cheapest blast-radius control: a workflow in orgA cannot read orgB's checkout directory or any files it leaves behind. Add systemd hardening (`ProtectSystem=strict`, `PrivateTmp=true`, `NoNewPrivileges=true`) per unit if the runners share a machine with anything else.
4. **Concurrency is per instance, and the box is the real bottleneck.** Each runner executes one job at a time, so two instances give two concurrent jobs — but CPU/RAM/disk are shared. Size job parallelism to the machine, or add more instances per org (same pattern, more names) when queueing appears; watch queue behavior as described in `infra/self-hosted-runner-queue-stuck.md`.
5. **Updates and cleanup are per directory.** Runner updates (`./config.sh --remove` + fresh install, or the runner's self-update) and pruning stale work directories under `_work` must be done inside each instance's directory. A cron that wipes `_work/*` older than N days per runner keeps the disk from filling since both orgs share it.

## Routing: runner groups and labels

1. **Labels are the routing key.** A job lands on a runner whose labels satisfy `runs-on`. With two orgs on one box this is naturally enforced — orgA's jobs can only ever see orgA's runners — but labels still matter *within* an org: tag instances by capability (`linux`, `docker`, `arm64`, `heavy`) and set `runs-on: [self-hosted, docker]` rather than bare `self-hosted` so capability mismatches fail fast instead of succeeding weirdly. Labels can be set at `config.sh` time or edited later in the org's runner settings UI/API.
2. **Runner groups are org-scoped access control, not a sharing mechanism.** Within each org, runner groups define *which repositories* may use which runners — e.g., a `core` group restricted to the two repos that genuinely need CI, while the default group stays empty. Configure via Organization Settings > Actions > Runner groups; an org-level group cannot reach into the other org, which is precisely the isolation you want from one physical box.
3. **Never route across the trust boundary by relaying.** If a job in orgB truly needs orgA's artifacts, do it through the API (upload/download artifacts, `gh api`, or a pull-based deployment), not by pointing orgB's workflow at orgA's runner or sharing a filesystem path. The two-instance design exists to keep the orgs' job execution separate; don't undo it for convenience.

## The security trade-off: self-hosted runners and public repos

1. **Fork PRs on public repos are code execution on your machine by strangers.** Anyone can open a PR against a public repo; if its workflows run on your self-hosted runner, untrusted code executes on hardware that also runs the *other* org's jobs and whatever else lives on that box. GitHub's hardening guidance is blunt: use self-hosted runners with private repositories; treat any public-repo exposure as a hostile configuration.
2. **If a public repo must use them, gate external contributors.** In that repo/org's Settings > Actions > General, require approval for workflows from all external contributors ("Require approval for all external contributors") so first-time fork PRs never auto-run, and keep the runner in a runner group scoped to that repo only. Maintain the allowlist actively — the gate is only as good as who is already approved.
3. **Assume the box is multi-tenant hostile even inside one org.** Jobs of different branches/PRs run sequentially on the same persistent runner: secrets exported in one job may linger on disk, and `_work` carries state across runs. Prefer ephemeral runners for this reason (next section); on persistent runners, never echo secrets to disk, and clean `_work` between heavy jobs.
4. **Defense-in-depth on the box itself.** Per-org service users (above), Docker `container:` jobs or full VM job isolation for anything touching third-party code, and — if the runners live in a home lab — an egress-restricted network segment, since a compromised runner is a permanent foothold inside your network.

## Persistent vs ephemeral, and when to graduate to ARC

1. **Persistent dual instances are the right *cheap* answer.** Warm caches, zero provisioning latency, and systemd are hard to beat for one box and two orgs. GitHub's own recommendation, though, is ephemeral runners — one job per runner, then destroy — because they eliminate cross-job state leakage and stale-runner drift; our persistent setup compensates with per-org users and `_work` cleanup.
2. **Scale-out on one box is just more instances.** The same directory/name/labels recipe adds a third or fourth instance (per org) when queue times grow — no orchestration needed until the machine saturates.
3. **When the box is the bottleneck, move to ARC, not to more boxes of this shape.** Actions Runner Controller on Kubernetes (ephemeral scale sets, `minRunners`/`maxRunners`) is the standard autoscaling answer, already documented in `infra/arc-github-runners-k8s.md`; the speedup playbook without weakening required checks is `github-actions-self-hosted-runners-2026.md`. The dual-instance systemd pattern remains the right tier below that: one machine, two orgs, zero dollars.

## Related

1. **`github/ci-budget-exhaustion-migration.md`.** The minutes-exhaustion decision path that motivates this setup, and the billing math behind it.
2. **`github-actions-self-hosted-runners-2026.md`.** Speedups, ephemeral runners, and keeping required checks intact on self-hosted capacity.
3. **`infra/github-self-hosted-runners.md`.** Runner concepts and single-org baseline setup.
4. **`infra/self-hosted-runner-queue-stuck.md`.** Diagnosing stuck queues when both orgs contend for one box.
5. **`github-actions-pull-request-target-poisoning.md`.** The workflow-level cousin of the fork-PR risk: untrusted input meeting privileged execution.
