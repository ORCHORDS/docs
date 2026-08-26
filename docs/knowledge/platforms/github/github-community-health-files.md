# github-community-health-files

**Issue:** A 30-repo organization has drifted into 30 slightly different CONTRIBUTING.md files, two repos with no SECURITY.md at all (so the Security tab shows no contact path), inconsistent issue templates, and a CODE_OF_CONDUCT that exists only where someone remembered to copy it. Every new repo starts from a stale template and reimplements the same governance text. GitHub solves this with a special public repository named `.github`: files there become organization-wide fallback defaults for any public repo that lacks its own — but the rules of what inherits, from where, and with what precedence are full of traps (CODEOWNERS and LICENSE do not inherit; issue templates override all-or-nothing; private `.github` repos do nothing).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What the `.github` repository is

1. **A public repo named exactly `.github`.** Create it as a normal public repository under the org with the literal name `.github`. Its README.md additionally renders as the organization profile README on the org homepage — the only place that README is used; it is not inherited by member repos.
2. **Fallback-only semantics.** Default files from `.github` apply only to repos that do not have their own version. Repo-level files always win; the org default is a floor, not a push.
3. **Public repos only.** Organization defaults work for public repositories; private member repos get nothing from the `.github` repo (the repo itself must also be public to act as a defaults source).
4. **Placement inside `.github`.** Supported default files can live in the `.github` repo's root, its `.github/` folder, or its `docs/` folder — except issue/PR templates, which must be under `.github/ISSUE_TEMPLATE/` (and `PULL_REQUEST_TEMPLATE` likewise under `.github/`).
5. **Also works for user accounts.** A personal public `.github` repo provides the same defaults for your own public repos — useful for solo-maintained portfolios.

## Which files inherit (and which don't)

1. **Text governance files that inherit.** CONTRIBUTING.md (linked when users open issues/PRs), CODE_OF_CONDUCT.md, SECURITY.md (surfaced on the Security tab), SUPPORT.md (Community standards / "Get help"), GOVERNANCE.md, FUNDING.yml (Sponsor button), and discussion category forms (YAML forms for Discussions categories).
2. **Issue and PR templates inherit as folders.** Default `ISSUE_TEMPLATE/*` (including issue forms and `config.yml` with contact links, blank-issue disabling, etc.) and `PULL_REQUEST_TEMPLATE/*` live in the `.github` repo under `.github/ISSUE_TEMPLATE/` and `.github/PULL_REQUEST_TEMPLATE/` respectively.
3. **CODEOWNERS does not inherit.** Despite widespread belief, CODEOWNERS is not in the supported defaults list — every repo needs its own CODEOWNERS (root, `.github/`, or `docs/`). Generate per-repo ones with scripting if consistency matters; see `branch-protection-and-codeowners.md`.
4. **LICENSE does not inherit.** License files must exist in each individual repository because they ship with clones and packages; an org-wide license default would change nothing legally.
5. **Watch the Community Standards check.** Each repo's Insights → Community page lists missing health files — after setting org defaults, public repos should show most items satisfied via inheritance, confirming the wiring works.

## Precedence and override traps

1. **Three-location order per repo.** GitHub looks in the member repo's `.github/` folder, then repo root, then `docs/` folder; the first match wins at that repo. Only if none exist does the org `.github` repo's file (same order) get used.
2. **Issue templates are all-or-nothing.** If a repo has any file in its own `.github/ISSUE_TEMPLATE/`, the org default template folder is ignored entirely — one local template silently disables every org default form. Plan "repo overrides template" migrations knowing this cliff.
3. **Labels referenced by default issue templates must exist in both repos.** A default template assigning `labels: [bug]` requires `bug` to exist in the `.github` repo and in each consuming repo, or label application silently fails.
4. **Symlink caveat.** Some teams symlink shared content between repos; the defaults mechanism does not follow symlinks in the `.github` repo — use real files.
5. **Caching lag.** Newly created/updated defaults can take a short while to appear in member repos' issue/PR forms; don't rewrite config chasing a caching artifact.

## Operating model that stays clean

1. **Treat `.github` as versioned governance.** Review changes to default templates via PR, exactly like code — every public repo's contributor experience changes when this repo merges.
2. **One canonical, per-repo escape hatch.** Document the inheritance rules in the `.github` repo's own README so maintainers know: local file wins, templates are all-or-nothing, CODEOWNERS/LICENSE are always local.
3. **Prefer issue forms over markdown templates.** In the default `ISSUE_TEMPLATE/` folder, structured YAML forms (with required fields, dropdowns, validations) yield triage-ready issues; link out to Discussions for questions (see `issue-and-pr-templates.md`, `github-discussions-2026.md`).
4. **Pair with repo templates.** Use a repo template (`github-repo-template-setup.md`) for files that cannot inherit (LICENSE, CODEOWNERS) and org `.github` defaults for everything else, so a new repo is compliant on creation.
5. **Audit periodically.** A monthly `gh api /orgs/ORG/repos` loop checking each repo's Insights → Community completeness (or `gh api repos/OWNER/REPO/community/profile`) catches drift where someone added a local file that shadowed a default unknowingly.
6. **Keep SECURITY.md aligned with practice.** If private vulnerability reporting is enabled org-wide, the inherited SECURITY.md must state that channel first — an inherited stale email address misdirects reports (see `github-security-advisories.md`).

## Related

1. **`issue-and-pr-templates.md`.** Form syntax and config.yml details that the defaults folder consumes.
2. **`github-organization-settings.md`.** Where `.github` repo defaults sit in the broader org policy picture.
3. **`github-security-policy-file.md`.** SECURITY.md content standards for the org-wide default.
