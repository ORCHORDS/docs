# API Contract Testing Pact Broker Versioning

Consumer-driven contract tests only prevent integration breakage if the contracts themselves are
stored, versioned, and matched to the versions of the software that produced them. A Pact
contract written by consumer 2.3.0 has meaning only against the provider version that verified
it and the deployment environments where those versions actually run. The Pact Broker exists to
hold this matrix together: contracts keyed by consumer name and version, provider verification
results keyed by provider version, and deployment records that tie both to environments. Teams
that treat the broker as a dumb file store, or that version contracts with meaningless
identifiers, lose the ability to answer the only question that matters — *is it safe to deploy
this version here?*

## Scope

Covers versioning strategy for Pact contracts and verification results in a Pact Broker or
PactFlow instance: what constitutes a consumer version number, how provider verification results
are recorded, how branches, tags, and environments interact, and how `can-i-deploy` gating is
wired into CI/CD. Applies to JavaScript, JVM, Go, Python, and .NET Pact implementations because
the broker contract is language-neutral. Does not cover writing the interactions themselves, nor
schema-diff tools that compare OpenAPI documents rather than executed contracts.

## Workflow or implementation guidance

1. **Choose a meaningful, monotonic consumer version number.** The broker matches records on
   `consumer version`, so a timestamp or a git SHA is acceptable but a non-monotonic label is
   not. Recommended practice is a semantic version with a build number appended — for example
   `1.4.0+3` — or a git commit SHA where the pipeline has no version concept. Whatever is
   chosen, it must be reproducible from the artefact: re-running the same commit must not
   produce a different version number, or verification history fragments.
2. **Publish the contract from CI, never from a laptop.** `pact-broker publish` (or the
   `pact-publish` step in the CLI) is called from the consumer pipeline after the test run,
   with the branch name recorded. Publishing from local machines creates records that cannot be
   traced to a build and cannot be replayed.
3. **Record the branch.** Modern broker versions key contract publication on the git branch,
   which lets the provider matrix show *which line of work* expects which interactions. Treat
   `main` as the integration branch; feature branches publish their own contracts so providers
   can detect breakage before merge rather than after.
4. **Verify on the provider side with the provider version recorded.** The provider pipeline
   fetches the pacts that concern it — all branch pacts for `main` verification, plus the pacts
   of deployed consumers — and publishes verification results with the provider's own version
   and branch. A verification result without a provider version is unusable for gating.
5. **Record deployments and releases.** Call `record-deployment` (or `record-release`) when a
   consumer or provider version lands in an environment. This is what converts a pile of
   verification results into a queryable question: the broker knows exactly which consumer
   versions are live in `production` and can therefore verify a provider candidate against the
   live set rather than against the tip of `main`.
6. **Gate with `can-i-deploy`.** Before deploying consumer or provider, run
   `pact-broker can-i-deploy --pacticipant <name> --version <version> --to-environment
   production`. It returns success only if the broker holds a verification of the relevant
   contract by a provider version compatible with what is in that environment. Wire the exit
   code into the pipeline as a hard stop.
7. **Prune with care.** Broker data accumulates. Use the version-interval and branch-head
   retention controls rather than deleting records ad hoc; deleting the last verification of a
   still-deployed consumer version breaks `can-i-deploy` for that version.

An illustrative consumer pipeline stage in a Node repository:

```yaml
- run: npm test -- --publish                       # runs PactV3 tests, publishes to broker
  env:
    PACT_BROKER_BASE_URL: ${{ secrets.PACT_BROKER_URL }}
    PACT_BROKER_TOKEN: ${{ secrets.PACT_BROKER_TOKEN }}
- run: npx pact-broker can-i-deploy --pacticipant storefront --to-environment production
```

The provider pipeline mirrors this: `pact-broker verify` with the provider version, then its own
`can-i-deploy` gate.

## Controls

- Every contract publication carries consumer version, branch, and a link back to the CI build.
- Every verification result carries provider version and branch.
- `can-i-deploy` gates both consumer and provider deployment pipelines to every named
  environment, and fails closed on missing verification results.
- Deployments and releases are recorded for each environment, so the broker's view of "what is
  live" stays true.
- Contract change review: a diff of the published pact against the previous version is included
  in the pull request, making it visible when a consumer demands a new interaction.
- Retention policy that keeps at least the records for currently deployed versions.

## Validation evidence

- Deliberately break a provider endpoint and confirm the consumer pipeline's `can-i-deploy`
  fails before the incompatible consumer ships — a rehearsal that proves the gate is wired, not
  assumed.
- The broker matrix page for each pair shows a contiguous verification history with no gaps
  around deployed versions.
- Version numbers in the broker match the artefacts deployed to environments exactly; spot-check
  by resolving a deployed version's build link.
- An audit of the last N merges shows each contract-changing pull request carried a visible
  contract diff.

## Failure modes and correction

- *Contracts published with the same version number for different content.* Fix the pipeline so
  the version derives from the commit plus build counter; purge the ambiguous records and
  republish.
- *Verification results published without a provider version.* They become invisible to
  `can-i-deploy`. Correct the provider pipeline and re-verify.
- *Tags used as pseudo-environments with mutated semantics.* Older tag-based workflows
  (`--tag production`) degrade when tags move. Migrate to recorded deployments and
  `--to-environment`, which the broker can reason about historically.
- *Deleting old records to save space.* If a two-year-old consumer is still deployed, its
  verification must survive. Prune by interval and by whether a version is deployed, not by age
  alone.
- *Feature-branch contracts ignored by the provider.* Configure the provider to verify branch
  pacts, or the consumer learns of breakage only after merge.
- *Broker treated as the source of truth for API design.* The contract describes observed
  interactions, not intent. Keep an OpenAPI or schema artefact for design-level discussion and
  use the broker for verified compatibility.

## Limitations

- Pact verifies request/response pairs the consumer actually exercises; interactions never
  exercised by any consumer test remain ungoverned.
- The broker reasons about versions it has been told about. Pipelines that deploy outside CI
  bypass the model entirely, and the gate cannot protect what it cannot see.
- `can-i-deploy` answers a compatibility question, not a functional one: a verified contract can
  still hide behavioural changes inside a response body that the matcher happened to tolerate.
- Generous matchers (for example matching any string) weaken the contract; versioning discipline
  cannot compensate for a contract that asserts almost nothing.
- Self-hosted brokers carry operational cost — upgrades, backups, and access control — that a
  team must actually staff.

## Canonical sources

- Pact Foundation, *Pact documentation* (consumer/provider workflows, broker concepts,
  can-i-deploy): https://docs.pact.io/
- Pact Foundation, *Pact Broker* (repository with deployment recording, matrix, and retention
  guidance): https://github.com/pact-foundation/pact-broker
- Pact Foundation, *Pact JS implementation*: https://github.com/pact-foundation/pact-js
