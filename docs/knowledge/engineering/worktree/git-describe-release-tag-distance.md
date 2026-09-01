# Tag-Distance Budgets: Using git describe as a Release Drift Alarm

## Scope

This article covers `git describe` as an operational signal rather than a version-string generator: interpreting the commit-count component as a drift measurement between releases, setting tag-distance budgets, choosing between annotated and lightweight tags so the output stays meaningful, and wiring the check into CI as a release-readiness gate. It applies to teams that cut releases from `main` or from release branches and want an early warning when a release is ballooning. It does not cover embedding describe strings into build artifacts, semantic-version automation, or changelog generation.

## Workflow or implementation guidance

`git describe --tags` walks back through ancestry from the current commit and emits `<tag>-<distance>-g<abbrev>`, for example `v2.9.0-41-g7c3a5b1`. The two data points are doing different jobs. The `g<abbrev>` segment identifies the exact commit. The distance — the number of commits reachable from HEAD but not from the tag — measures how far the tree has traveled since the last marker. Teams read the first constantly and ignore the second, which is the missed opportunity: distance is the cheapest drift metric a repository produces for free.

**Treat distance as a release-size budget.** Decide, per repository, the maximum number of changes you are willing to ship in one release. That number is a risk-management decision, not a tooling preference: a release containing 400 commits carries 400 chances for a regression and is nearly impossible to bisect against if something breaks in staging. A common calibration for a service deployed continuously is a distance budget of 50 to 150; for a versioned SDK with heavier release ceremony, 20 to 60. Whatever the number, write it down and enforce it mechanically:

```bash
DISTANCE=$(git describe --tags | sed -E 's/.*-([0-9]+)-g[0-9a-f]+$|\1/')
```

Then fail the release workflow when `DISTANCE` exceeds the budget, or — the softer variant — require a second approver on the release when it does. The alarm's value is forcing the conversation: either cut now, or consciously accept a large release with eyes open.

**Tag type changes the semantics.** `git describe` prefers annotated tags. An annotated tag is a real object with a tagger, a date, and a message; a lightweight tag is a named pointer. Bare `git describe` reports only annotated tags, which means a team that cuts releases with `git tag v2.9.0` (lightweight) gets either nothing or a distant ancestor tag, and the distance number silently measures against the wrong marker — often the previous annotated tag from months ago, inflating or corrupting the metric. Two fixes, pick one deliberately: create release tags annotated (`git tag -a v2.9.1 -m "release 2.9.1"`), or pass `--tags` so lightweight markers count and accept that throwaway tags (like `test-tag` pushed by an experiment) can pollute the reference point. For a distance budget, annotated-only is the disciplined default because it is hard to create one accidentally.

**Guard the corner cases in CI.** Three failure shapes break naive scripts:

- *No reachable tag at all* — a fresh repository or a branch off before the first tag. `git describe` errors out; add `--always` so it degrades to the abbreviated hash instead of failing the script for a non-reason.
- *Shallow checkout* — `actions/checkout` defaults to depth 1, so the history walk finds nothing. Set `fetch-depth: 0`, or at minimum fetch tags explicitly with `git fetch --tags --depth=...`, or the describe call fails or returns nonsense.
- *Dirty working tree* — during a local cut, uncommitted changes make the string misleading. `--dirty=-dirty` appends a visible suffix so the state is at least labeled rather than hidden.

**Use describe to triage "what is actually running."** When an incident report says "the API started misbehaving after Tuesday's deploy," the describe string of the running build answers which commit it is, and the distance tells you how many changes since the previous known-good tag are suspects. That number bounds the bisect: a distance of 12 makes `git bisect` a four-step binary search; a distance of 400 makes manual triage a project. This is the concrete, human payoff of the budget — releases held small are releases that can be debugged.

**Watch the branch trap.** `git describe` follows ancestry from HEAD only. On a long-lived release branch whose tags live on `main`, describe finds an ancient merge base and reports an inflated distance that has nothing to do with release size. The remedy is to tag the release branch itself at each cut (annotated), so the walk has a nearby anchor. If the branch is `release/v3`, its `v3.4.1` tag is the reference the next cut measures against.

## Controls

- Every repository declares a numeric tag-distance budget in its release workflow file, visible to reviewers.
- Release tags are annotated by convention; CI rejects pushing a lightweight tag matching the release pattern (`git for-each-ref refs/tags --format='%(refname:short) %(objecttype)' | grep 'tag$'` inverted check).
- Release CI runs with full history and tags (`fetch-depth: 0` plus `--tags`), and the describe step uses `--always --dirty=-dirty` guards.
- Exceeding the budget either blocks the cut or flips the release to a two-approver path — the escalation is written into the workflow, not negotiated in chat.
- Release branches carry their own annotated tag per cut so distance measures the right interval.

## Validation evidence

- Immediately after tagging a release, `git describe` on the tagged commit emits the bare tag with distance zero — `v2.9.1` with no `-N-g` suffix. Any nonzero suffix on a fresh cut means the tag was placed on the wrong commit.
- The distance reported equals `git rev-list --count <tag>..HEAD` for the same tag; checking the two against each other on a scratch branch validates the parsing pipeline end to end.
- A deliberately shallow clone (`git clone --depth 1`) fails or truncates the describe step, and the CI guard catches it — proving the `fetch-depth` setting is load-bearing rather than decorative.
- Annotate a test tag, delete it, and re-create it lightweight: the describe output changes which tags it considers, demonstrating the annotated-only default to whoever maintains the script.
- Incident drill: given a running build's describe string, resolve it to a commit, confirm `git bisect start <bad> <good-tag>` needs only log2(distance) steps, and record that number as the expected triage cost for the current budget.

## Failure modes and correction

- **Silent lightweight tags.** Release tags created without `-a` make bare `git describe` skip them, and the budget measures against a months-old reference. Correction: annotated-only convention plus the CI objecttype check that rejects lightweight tags matching the release pattern.
- **Inflated distance on release branches.** The branch cut measures from a `main` tag across a merge base, reporting hundreds when the release contains twelve changes. Correction: tag each cut on the branch itself; describe then measures branch-local intervals.
- **Shallow-checkout nonsense.** The describe step errors or returns a hash with no distance, and the budget check silently passes on zero information. Correction: `--always` is for degradation, but release workflows must fetch full history and fail loudly if tags are absent.
- **Budget without consequence.** The distance prints green in the log while releases keep growing, because exceeding the budget only warns. Correction: wire the threshold to the approval path; a metric nobody must act on is a log line.
- **Deleted or moved tags.** Someone force-updates a release tag to add a missed commit, and old describe strings now resolve to different content. Correction: protected tags via rulesets; tag history is append-only.

## Limitations

Distance counts commits, not risk: fifty trivial dependency bumps and fifty rewrites of the auth flow both report fifty. The metric also depends entirely on tagging discipline — skipped or irregular tags corrupt the interval being measured, and the budget inherits that fragility. On monorepos with release-please or changesets, the tag points at a generated version-bump commit, so distance includes automation commits and slightly overstates human change volume. `git describe` walks first-parent-ish ancestry from HEAD only, so it says nothing about work merged into sibling branches, and multi-branch release matrices need per-branch budgets. Finally, the absolute numbers in any budget are heuristics; they must be recalibrated against each team's actual change-failure experience rather than imported wholesale.

## Canonical sources

- Git documentation — git-describe (output format, annotated-tag preference, --always/--tags/--dirty): https://git-scm.com/docs/git-describe
- Pro Git, 2nd edition — Git Basics: Tagging (annotated vs lightweight): https://git-scm.com/book/en/v2/Git-Basics-Tagging
- Git documentation — git-rev-list (counting the tag..HEAD interval independently): https://git-scm.com/docs/git-log
- GitHub Docs — Protected branches and rulesets for guarding tags: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets
