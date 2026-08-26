# trunk-based-development-2026

**Issue:** A team debates Git Flow vs GitHub Flow vs trunk-based. The team has long-lived feature branches with merge conflicts. The team needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 branching models compared

| Model | Branches | Release cadence | Best for |
|---|---|---|---|
| Trunk-based | main + short-lived feature | Continuous | High-cadence teams |
| GitHub Flow | main + feature | Per-PR deploy | Web apps, SaaS |
| Git Flow | main + develop + feature + release + hotfix | Versioned | Versioned software |
| GitLab Flow | main + environment | Per-env | Multi-environment |

## The 5 trunk-based rules

1. **One main branch** (or `main` + `release/x` for prod-fix branches).
2. **Feature branches live <1 day** ideally, max a few days.
3. **Small, frequent merges** to main.
4. **Feature flags** decouple deploy from release.
5. **No long-lived branches.** Even release branches are short-lived.

## The 5-step adoption pattern

1. **Adopt feature flags** (LaunchDarkly, Unleash, in-house).
2. **Shorten branch lifetime** to <1 day.
3. **Automate tests** for confidence on every merge.
4. **Pair/mob** on big features instead of long branches.
5. **Sunset old branches** weekly.

## The 5 anti-patterns

1. **Long-lived feature branches** with merge hell.
2. **Release branches lasting months** with cherry-pick cycles.
3. **Manual QA gates** blocking merges.
4. **No feature flags** tying deploy to release.
5. **Develop + main** with parallel lives.

## Gotchas

- Trunk-based requires strong CI; without it, you ship broken code to everyone.
- Feature flags add complexity; budget for flag cleanup.
- Pair/mob on big features works for some teams, not all.
- "Trunk" can be `main` or `develop` depending on the team; the rule is one trunk.
- Some regulated industries require separate validation branches for compliance.

## Source URLs (verified 2026-08-10)

- https://trunkbaseddevelopment.com/
- https://docs.github.com/en/get-started/quickstart/github-flow
- https://nvie.com/posts/a-successful-git-branching-model/
- https://martinfowler.com/articles/branching-patterns.html
