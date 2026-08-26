# consumer-contract-deploy-gates

**Issue:** Integration tests that spin up the whole world are slow, flaky, and still miss the failure mode that matters most: a consumer deploys a change whose expectations its provider has not yet satisfied — or a provider ships a change that breaks a consumer nobody told them about — and production breaks even though every service passed its own test suite. Consumer-driven contract testing decouples the two sides: consumers publish contracts (Pacts) encoding exactly the requests and response fields they depend on, providers verify those contracts against their real implementations, and a broker maintains the compatibility matrix between every consumer version and provider version. The deploy gate — can-i-deploy — turns that matrix into enforcement: before a version ships, the pipeline asks the broker whether that exact version is verified against everything currently deployed in the target environment, and blocks the deploy if not. Cross-team compatibility stops being hope and becomes a query.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The contract workflow

1. **Consumer tests generate contracts.** The consumer's unit tests run against a mocked provider and produce a contract file capturing real request/response expectations — fields relied upon, not fields that exist. Because the mock is generated from these expectations, the contract is executable documentation of what the consumer actually needs.

2. **Publish contracts versioned by commit SHA.** Each consumer build publishes its contracts to the broker tagged with the exact git SHA that produced them. SHA versioning makes every verification result traceable to code, and it is what later lets can-i-deploy answer for a specific deployable version rather than a branch name that keeps moving.

3. **Provider verification against real code.** The provider pipeline replays every consumer contract against the provider's actual implementation (real handlers, real serialization) and records pass/fail per consumer version back to the broker. This is where silent breakage is caught: a renamed field or tightened validation fails the replay before any environment is touched.

4. **The broker as the source of truth.** The broker is not a cache — it is the coordination point holding the matrix of which consumer versions are verified against which provider versions, and which versions are deployed where. All gate decisions read from it; nothing decides compatibility from local state.

## The can-i-deploy gate

1. **Pre-deploy compatibility query.** Immediately before deploying consumer version X to environment E, run can-i-deploy for X against the provider versions currently recorded as deployed in E. The gate fails the deploy when the pair is unverified, which is precisely the pair production would otherwise test for you.

2. **record-deployment after every deploy.** Each successful deploy records the newly live version into the broker's environment records. Deployments, not intentions, define the baseline that future gates check against; skipping the record step silently corrupts every later decision.

3. **Environment tracking over manual tags.** Older workflows tagged pacts with environment names; the supported model is record-deployment (and record-rollback where used). Tags drift and collide, while recorded deployments reflect what actually happened in each environment.

## Wiring into CI/CD

1. **Separate build and deploy stages.** Contracts are published and verified during CI (build), while can-i-deploy and record-deployment run in the deploy stage for each target environment. Collapsing them into one stage either blocks merges on production state or, worse, skips the gate for later manual deploys.

2. **Fail fast on PRs, not at deploy time.** Run contract verification on every PR so a breaking change is visible to its author within minutes, complete with the Pact Broker diff showing exactly which expectation broke. The deploy gate is the backstop; the PR check is where you want failures to happen.

3. **Handle breaking changes deliberately.** Coordinated breaking changes (new required header, removed endpoint) need a process: provider verifies against the consumer's main-branch contract, consumer ships first or behind coordination, and pending verification failures can be temporarily acknowledged with expiry dates in the broker rather than permanently ignored.

## Governance and failure modes

1. **Retire orphaned contracts.** When a consumer is decommissioned, delete its contracts; otherwise providers keep verifying and gating against ghosts, and a legitimate provider change gets blocked by a consumer that no longer exists. Broker webhooks can flag contracts with no verifying activity for N days.

2. **Decide gate-outage policy in advance.** When the broker is unreachable, choose fail-open (deploy with a tracked exception) or fail-closed (block deploys). Fail-closed is safer but couples deploys to broker availability; whichever you choose, make it a written decision rather than an incident-time improvisation.

3. **Do not let contracts replace integration tests entirely.** Contracts verify message shape and status expectations between pairs; they do not verify end-to-end business flows, auth, or infrastructure. Keep a thin layer of end-to-end smoke tests and let contracts carry the combinatorial load they are good at.
