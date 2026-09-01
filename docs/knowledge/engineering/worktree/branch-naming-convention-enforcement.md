# Branch Naming Convention Enforcement

## Scope

This article covers the definition and enforcement of a branch naming convention: the grammar for branch names, where enforcement belongs (client hook, CI check, server-side rule, or ruleset), how to roll a convention out without breaking in-flight work, and how to keep the convention from becoming theater. It applies to repositories with multiple contributors where branch names feed automation — PR templates, preview environments, ticket linkage, changelogs. It does not cover branch strategy selection, merge policy, or branch protection beyond the narrow question of name enforcement.

## Workflow or implementation guidance

A branch naming convention earns its keep only if machines consume it. If nothing parses the branch name, the convention is pure overhead and should be deleted rather than enforced. Start by listing what the name must encode, then derive the grammar.

A proven grammar for a team using tickets and preview environments:

```
<type>/<ticket>-<slug>
```

Examples: `feat/PLAT-412-merge-queue-batching`, `fix/WEB-88-cookie-encoding`, `chore/deps-bump-wrangler`. The type vocabulary is small and fixed: `feat`, `fix`, `chore`, `docs`, `refactor`, `perf`, `test`, `release`, `hotfix`. The ticket segment is required when the team tracks work in a tracker, optional otherwise. The slug is lowercase kebab-case, limited to around forty characters, because branch names appear in URLs, in CI log headers, and in preview-environment hostnames — all of which have length or character constraints.

Two rules prevent most downstream pain. First, forbid characters that break shells and URLs: spaces, colons, asterisks, question marks, brackets, backslashes, and non-ASCII characters. Git accepts most of these, which is exactly why the convention must reject them before a tool does it for you, badly. Second, forbid consecutive slashes and trailing slashes; some tooling treats the first path component as a namespace, and empty components confuse it.

Enforcement belongs in layers, cheapest-failing first.

**Layer 1 — client-side check on branch creation.** A post-checkout or a wrapper script validates the name at creation time, failing within a second of the mistake. This is advisory only: contributors can skip hooks, and clones without the hook exist. Its job is fast feedback, not security.

**Layer 2 — CI check on push.** A workflow step runs on every push to a non-default ref, validates the ref name against the grammar, and fails with a message telling the contributor the expected pattern and the exact rename command: `git branch -m old-name new-name && git push origin :old-name new-name`. Failing here is cheap — no review time has been spent.

**Layer 3 — server-side restriction.** A ruleset or branch-name pattern restriction on the default branch's protection configuration rejects pushes that create nonconforming refs. This is the guarantee, and it is the only layer that cannot be bypassed by a contributor with a clean clone.

The layering is deliberate: layer 1 catches the mistake in one second, layer 2 catches it before review, and layer 3 makes the rule impossible to route around. Teams that install only layer 3 get correct names but terrible contributor experience, because the error surfaces after the developer has done all the work of pushing.

Rollout, not decree: run layer 2 in report-only mode for two weeks, collect the list of violations, and let owners of in-flight branches rename at their convenience. Then enable enforcement. A convention that breaks ten open PRs on day one will be reverted by the team that owns those PRs.

Exempt namespaces explicitly. `release/*`, `hotfix/*`, `renovate/*`, `dependabot/*`, and `gh-pages` follow other conventions by design; write the exemption list into the same configuration as the grammar so the exceptions and the rule live together. Also exempt automation-created branches in CI configuration, since bots create refs programmatically and their names follow their own schemes.

Finally, name the tooling once. Whether the check is a small script in the repository or a shared action, there must be exactly one implementation of the grammar. Duplicated regexes in the hook, the workflow, and the ruleset drift apart, and the drift always shows up as a contributor blocked by a rule nobody can explain.

## Controls

- One grammar definition, held in a single shared script or action, referenced by every enforcement layer.
- Client hook for instant feedback, clearly documented as advisory.
- CI check on push with an actionable failure message including the rename command.
- Server-side ruleset restricting which ref names may be created, as the unbypassable layer.
- An explicit exemption list for release, hotfix, and automation namespaces.
- A two-week report-only rollout window before enforcement, with an owner list of violating branches.

## Validation evidence

Verification is mechanical and continuous. Run these checks and treat regressions as defects in the enforcement configuration:

- Push a branch matching each allowed type from a scratch clone and confirm CI passes the name check.
- Push branches with each forbidden character class — space, colon, non-ASCII, double slash, missing type prefix, uppercase slug — and confirm each is rejected with the actionable message at layer 2 and rejected again at layer 3.
- Confirm the exemption list behaves: `release/v2.4.0` and `renovate/wrangler-4.x` pass all layers.
- After rollout, query the repository's ref list monthly and count nonconforming names; the number should be near zero and composed only of pre-rollout branches grandfathered by policy.
- Confirm a single source of truth for the grammar by searching the repository for duplicate regexes; more than one implementation is a finding.

## Failure modes and correction

- **Convention without a consumer.** Names conform but nothing parses them. Correction: wire the ticket number into PR titles and the changelog, or delete the grammar.
- **Bypass accumulation.** Contributors push nonconforming names through a path the ruleset missed — often the first push of a new branch from a fork. Correction: audit the ref list monthly and close the specific bypass.
- **Regex drift.** Hook, CI, and server rules disagree, so a name passes one and fails another. Correction: collapse to one implementation; the other layers call it.
- **Day-one breakage.** Enforcement enabled while long-lived branches violate the grammar. Correction: report-only window, published rename instructions, and a stated cutover date.
- **Vocabulary sprawl.** Types multiply from eight to thirty as teams add `spike`, `poc`, `wip`, `demo`. Correction: cap the type list, route everything else to `chore` or `feat`, and require a documented reason to add a type.

## Limitations

Name enforcement guarantees nothing about branch content, lifetime, or merge readiness — a perfectly named three-week-old branch is still a process problem this convention cannot see. Ruleset capabilities differ between Git hosting platforms and plan tiers, so layer 3 may be unavailable or weaker on some setups; in that case layer 2 is the strongest guarantee and the monthly ref audit carries the load. The grammar assumes a ticket-oriented workflow; repositories without a tracker need the ticket segment dropped, which weakens traceability accordingly. Client-side hooks do not travel with clones, so layer 1 coverage is best-effort by nature. None of this replaces review of what is actually on the branch.

## Canonical sources

- Git documentation — git-branch (ref name rules and listing): https://git-scm.com/docs/git-branch
- Git documentation — git-check-ref-format is the authority on valid ref names; see the references section of https://git-scm.com/docs/git-push
- GitHub Docs — Creating and deleting branches within your repository: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-and-deleting-branches-within-your-repository
- GitHub Docs — About rulesets (server-side ref restrictions): https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
