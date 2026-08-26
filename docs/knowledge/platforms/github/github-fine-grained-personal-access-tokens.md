# github-fine-grained-personal-access-tokens

**Issue:** GitHub fine-grained PATs vs classic PATs
**Date:** 2026-08-09
**Status:** documented

## Symptom
You issue a `ghp_…` classic PAT. It's repo-wide.
`"All repositories"`. You realize it's 100x more
powerful than your script needs. You need fine-grained.

## Root cause
**Classic = broad. Fine-grained = scoped.** Migrate.

**Source:** GitHub auth docs 2026.

## The "PAT types" concept

PAT types:
- **`ghp_`:** Classic (legacy)
- **`github_pat_`:** Fine-grained
- **`ghs_`:** GitHub App installation
- **`gho_`:** OAuth user
- **`ghu_`:** User-to-server
- **`ghc_`:** (deprecated)

The 5 are the prefixes.

## The "fine-grained" pattern

For fine-grained:
- **Repos:** Select specific
- **Permissions:** Granular (100s)
- **Expiration:** Required
- **User:** Owned
- **Use:** Default for new

The fine-grained is default.

## The "scope minimum" pattern

For scope:
- **Repos:** One (or few)
- **Permissions:** Minimum
- **Example:** `Contents: Read`
- **Not:** Full `repo`
- **Why:** Blast radius

The scope is minimum.

## The "expiration" pattern

For expiry:
- **Required:** Fine-grained
- **Pick:** Shortest that works
- **Max:** 1 year
- **Why:** Rotation
- **Cadence:** Scheduled

The expiry is set.

## The "one token per machine" pattern

For per identity:
- **Local dev:** One
- **CI:** One
- **Server:** One
- **Why:** Rotate independently
- **Why:** Traceable

The token is per machine.

## The "store securely" pattern

For storage:
- **CI secret:** Platform manager
- **Local:** `gh auth login --secure-storage`
- **Not:** `.env` committed
- **Not:** Shell history
- **Why:** Same as password

The storage is secure.

## The "audit tokens" pattern

For review:
- **Settings:** Developer settings
- **Org audit:** Token list
- **Revoke:** Unused
- **Cadence:** Quarterly
- **Why:** Stale = risk

The audit is scheduled.

## The "vs GitHub App" pattern

For shared:
- **App:** Per org
- **Installation token:** `ghs_…`
- **Expiry:** 1 hour
- **Use:** Cross-team
- **Why:** No personal token

The app is for shared.

## The "secret scanning" pattern

For leaks:
- **Default:** `github_pat_` in patterns
- **Push protection:** On
- **Why:** Auto-detect
- **When:** Public + private

The scan is enabled.

## The "stateless ghs_" pattern

For App:
- **Format:** `ghs_APPID_JWT`
- **2026-04-27:** Staged rollout
- **Why:** Per-app
- **Note:** New installs only

The format is updating.

## The "org policy" pattern

For org:
- **Restrict:** Classic PAT
- **Require:** Approval
- **Enforce:** Expiry
- **Why:** Default deny
- **2026:** Tighter

The policy is per org.

## The "still use classic" anti-pattern

For classic:
- **Issue:** Broad scope
- **Fix:** Migrate to fine-grained

The classic is legacy.

## The "all repos + full repo" anti-pattern

For broad:
- **Issue:** Single script, full access
- **Fix:** One repo + Contents: Read

The scope is minimum.

## The "no expiration" anti-pattern

For long:
- **Issue:** Never rotates
- **Fix:** Scheduled expiry

The expiry is set.

## The "shared personal token" anti-pattern

For share:
- **Issue:** Trace = personal
- **Fix:** GitHub App

The share is via App.

## The "in image" anti-pattern

For Docker:
- **Issue:** Token baked in
- **Fix:** Mount at runtime

The mount is runtime.

## The "in dotfile" anti-pattern

For dotfile:
- **Issue:** Committed
- **Fix:** Secret manager

The store is secure.

## The "no audit" anti-pattern

For never:
- **Issue:** Stale tokens
- **Fix:** Quarterly

The audit is recurring.

## The "single long-lived" anti-pattern

For one token:
- **Issue:** Dev + CI = both leak
- **Fix:** Per machine

The token is per identity.

## The "PAT checklist" pattern

For checklist:
- [ ] Fine-grained, not classic
- [ ] One repo (minimum)
- [ ] Minimum permission
- [ ] Expiration set
- [ ] One per machine
- [ ] Secure storage
- [ ] Quarterly audit
- [ ] No in-repo
- [ ] No in-image
- [ ] GitHub App for shared
- [ ] Push protection on

The checklist is 11.

## Verification
- **Test:** Scope is minimum
- **Test:** Expiry set
- **Test:** No leaks
- **Audit:** Quarterly

## Gotchas
- **The "classic" anti-pattern.** Fine-grained.
- **The "all repos" anti-pattern.** One.
- **The "no expiry" anti-pattern.** Set.

## Related
- `github/pat-self-merge-workaround.md`
- `github/github-actions-monorepo-caching.md`
- `github/branch-protection-and-codeowners.md`
- `security/secrets-management-comparison.md`
- `infra/secrets-rotation-runbook.md`
- `github/github-copilot-coding-agent.md`
- GitHub Docs: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-fine-grained-personal-access-tokens
- Manage: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens
- Token prefixes: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-token-prefixes
