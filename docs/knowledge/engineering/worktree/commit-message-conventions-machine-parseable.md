# Commit Message Conventions Machine-Parseable

## Scope

This article covers commit message conventions designed for machine parsing: the exact grammar, how tools consume each field, where enforcement lives, and how to keep the convention honest as automation multiplies. It applies to repositories whose changelogs, version bumps, release notes, and ticket linkage are generated from commit history. It does not cover general writing style for commit bodies, branch naming, or the choice of squash versus merge-commit policy.

## Workflow or implementation guidance

A commit message is a user interface for future automation, and the parser is the user. Write the convention for the parser first and the human second — the human reads anything, the parser reads exactly what you promised.

The baseline grammar is the Conventional Commits shape:

```
<type>(<optional scope>)<!>: <subject>

<body>

<footer trailers>
```

Field by field, what each one is for and the rules that keep it parseable.

**Type.** Lowercase, from a fixed vocabulary: `feat`, `fix`, `perf`, `refactor`, `docs`, `test`, `build`, `ci`, `chore`. The type is the version-decision field — `feat` maps to a minor bump, `fix` to a patch, and the tooling reads nothing else to decide. Rule: the vocabulary is closed. Adding a type is a breaking change to your own tooling, because every consumer has the old list compiled in.

**Scope.** Optional, parenthesized, lowercase, no spaces: `feat(api)`, `fix(auth)`. Scope routes changelog entries into sections and lets monorepos attribute changes to packages. Rule: if scopes are used, maintain an allowlist, because a typo'd scope silently creates a new changelog section forever.

**Breaking marker.** The `!` after scope, or `BREAKING CHANGE:` in the footer. Both must trigger a major-bump decision in tooling. Pick one as canonical for tooling and treat the other as a courtesy synonym; supporting both forever is how parsers grow bugs.

**Subject.** Imperative mood, no trailing period, and — the rule most often violated — no issue keys, no ticket IDs, no task numbers. The subject goes into changelogs and release notes verbatim, and a changelog full of `fix: PLAT-412 null deref in parser` is a changelog nobody reads. Ticket linkage belongs in the footer, where tooling that needs it can find it and tooling that does not can ignore it.

**Body.** Free-form, wrapped at seventy-two characters. Wrap for the parser-adjacent reason that tooling which renders commits into notes sometimes truncates on long lines, and for the human reason that terminals are still eighty columns wide. The body explains why, not what — the diff already says what.

**Footer trailers.** Key-value pairs, one per line, following the Git trailer format. The load-bearing trailers in practice: `Refs: PLAT-412` for ticket linkage, `BREAKING CHANGE: <description>` for breakage, `Reviewed-by:` and `Signed-off-by:` where governance requires them. Rule: trailers use the exact key spellings your tooling greps for; `Ref:` and `Refs:` are different strings to a machine.

Three practices separate conventions that survive from conventions that decay.

First, enforcement is mechanical and runs before the commit exists. A commit-msg hook validates the grammar in the second after the message is written, and a CI check validates it again on push as the backstop for clones without hooks. Human reviewers checking message format is a waste of the most expensive review seconds available.

Second, squash merges must preserve the convention. If the merge policy squashes to a single commit, the PR title becomes the commit message — so the PR title lint replaces the commit lint as the real gate, and the PR template prompts for the conventional format. Teams that lint commits but squash with the PR title as-is have a convention that applies to nothing.

Third, generated commits follow the same grammar. Dependency bots, release bots, and CI commits all produce messages. Configure them to conform — `chore(deps): bump wrangler from 3.90.0 to 4.20.5` — or exclude their branches from enforcement deliberately. An exempted bot that writes malformed messages teaches every new contributor what the convention really tolerates.

What breaks parsing in practice, in rough order of frequency: subjects containing ticket keys, scope typos creating phantom sections, type vocabulary drift after tooling updates, bodies with unwrapped lines that fold oddly in notes generation, and trailers using colons or spaces incorrectly. Every one of these is a hook away from never happening.

Finally, decide consciously what the convention is for. If nothing consumes your history — no changelog, no version automation, no ticket mining — then a full conventional grammar is ceremony, and a lighter convention with a good subject line serves the humans better. Machines justify the grammar; the grammar does not justify the machines.

## Controls

- Closed type vocabulary and scope allowlist, each versioned with the tooling that reads them.
- Ticket keys and metadata live in footer trailers, never in the subject.
- Commit-msg hook validates grammar locally; CI validates on push as the backstop.
- For squash-merge policies, the PR title lint is the real gate and the PR template prompts the format.
- Bot- and CI-generated commits either conform or are explicitly exempted by branch in the enforcement configuration.
- One canonical breaking-change marker for tooling, documented as such.

## Validation evidence

Verification is mechanical, cheap, and should run on every merge to the default branch:

- CI parses each new commit (or PR title, under squash) against the grammar and fails on violation; run it over a month of history and confirm the violation count trends toward zero.
- Generate the changelog from history and read it as a human would — every entry should be a sentence without ticket noise. Any entry containing a ticket key in the subject is a convention failure, not a style choice.
- Confirm version automation decisions: a history containing only `fix` commits must produce a patch bump; a `feat` must produce a minor; a breaking marker must produce a major. Test this against the release tooling in a dry run, not by publishing.
- Verify trailer extraction: pick ten merged changes and confirm the ticket system's linkage and the commit's `Refs` trailer agree.
- Check the exemption list against actual bot commits monthly — exempted branches producing malformed messages either get configured to conform or the exemption grows.

## Failure modes and correction

- **Ticket soup in subjects.** Changelogs become unreadable. Correction: hook rejects issue keys in the subject; the footer trailer carries linkage.
- **Scope sprawl.** Twenty scopes, nine of them typos, each generating its own changelog section. Correction: scope allowlist enforced by the hook, with additions as a reviewed configuration change.
- **Vocabulary drift.** Someone adds `improvement` and old tooling ignores the commit. Correction: the closed vocabulary is enforced; new types require updating every consumer in the same change.
- **Convention that governs nothing.** Messages conform perfectly, but no tool consumes them. Correction: either wire changelog and version automation to history or consciously downgrade the convention.
- **Squash blind spot.** Commit lint passes, squash merge writes the PR title verbatim, and the merged history violates everything. Correction: gate the PR title under squash policies.
- **Decorative bodies.** Multi-paragraph bodies restating the diff, slowing every future reader. Correction: body guidance is why over what; reviewers push back on narration.

## Limitations

A parseable convention guarantees structure, not truth — a `fix:` type on a change that actually breaks behavior produces a wrong version bump with perfect grammar, which is worse than no automation because it is trusted. Enforcement at the commit-msg hook does not travel with clones, so CI must carry the guarantee. Merge-commit policies complicate history parsing because merge commits themselves carry nonconforming messages and must be excluded by the tooling. The trailer format assumes Git trailer semantics; tooling that greps raw text will misparse bodies that merely contain trailer-shaped lines. The seventy-two-column and imperative-mood rules serve humans and marginal tooling; they are conventions, not parser requirements, and teams can relax them without breaking automation.

## Canonical sources

- Conventional Commits — Specification v1.0.0: https://conventionalcommits.org/en/v1.0.0/
- Git documentation — git-commit (message format and trailers): https://git-scm.com/docs/git-commit
- Git documentation — git-interpret-trailers, referenced from the git-commit manual: https://git-scm.com/docs/git-interpret-trailers
- GitHub Docs — About merge methods on GitHub (squash and commit message handling): https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github
