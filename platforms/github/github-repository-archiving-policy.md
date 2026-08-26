# github-repository-archiving-policy

**Issue:** Orphaned repositories accumulate in every organization: prototypes, retired services, duplicated migrations. Leaving them active invites security exposure (unpatched dependencies, live webhooks, standing access), pollutes code search and repo pickers, and misleads newcomers about what is production. GitHub's archive feature makes a repository read-only, but archiving has sharp operational edges — settings freeze, transfer blocks, Issues/PRs lock — and archiving is often mistaken for backup. An org needs an explicit lifecycle policy covering when to archive, what to do first, and how archived repos relate to the GitHub Archive Program and real backups.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What Archiving Actually Does

1. **Read-only tombstone.** An archived repository cannot receive pushes, issues, PRs, comments, or releases; stars, forks, and clones still work. GitHub search excludes archived repos from default code search results, and the banner makes the unmaintained state obvious to anyone landing on it.
2. **Settings freeze.** Most settings — branch protection, webhooks, actions permissions, secrets — cannot be modified while archived. Anything you want to change (disable Actions, revoke deploy keys, rotate secrets) must be done before archiving or by temporarily unarchiving.
3. **Structural limits.** You cannot transfer an archived repo or attach it elsewhere without unarchiving first; fork relationships persist; Pages sites of archived repos stay up as static content until disabled. Plan retirement steps around unarchive → change → re-archive cycles.
4. **Reversibility.** Unarchiving restores full function including old issues; nothing is deleted. This makes archiving a safe default action compared to deletion, which is irreversible and loses Issues/PR history permanently.
5. **Visibility of archived code.** Archived public repos remain publicly cloneable and are covered by the GitHub Archive Program's long-term preservation, but they no longer receive CI, Dependabot updates, or maintenance of any kind — treat their dependencies as permanently vulnerable.

## Pre-Archive Checklist

1. **Close or redirect open issues and PRs.** Locking issues on archive makes them permanently unanswerable; bulk-close with a pointer comment to the successor repo first (a script over the REST `PATCH /repos/{owner}/{repo}/issues` endpoint beats clicking).
2. **Update README and description.** State that the project is archived, why, where the replacement lives, and whether critical fixes will be cherry-picked. This is the highest-value minute of the whole process.
3. **Disable integrations.** Delete webhooks, revoke GitHub App installations, remove deploy keys and fine-grained PAT access to the repo, and disable Actions/Workflows so no stale scheduled workflow lingers. Secrets cannot be read while archived but rotate anything sensitive anyway.
4. **Export what must survive.** Archiving is not backup. Create `git clone --mirror` bundles or push a mirror to the successor org; export Issues/PRs via API or a tool if the discussion history matters, because deletion later would erase it.
5. **Record metadata.** Note the archive date, owning team, and reason in the README or an org-level registry so future audits know whether the repo can be deleted outright after retention expires.

## Org Policy Design

1. **Trigger criteria.** Public-sector examples like the VA GitHub handbook policy archive repos after a fixed inactivity window (e.g., no commits, issues, or releases for 6-12 months) combined with an owner confirmation; codify your own window and give owners a 30-day objection period before automated archiving.
2. **Tiered end-of-life.** Distinguish soft retirement (repo stays active, README marked deprecated) from archive (read-only) from deletion (after retention, e.g., archived 12+ months with no clone traffic and no compliance hold). This ladder prevents premature lock-in and endless zombie repos alike.
3. **Ownership and audit.** Require every repo to have a CODEOWNERS-backed owning team; quarterly access reviews sweep repos whose owning team no longer exists. An unowned active repo is an archiving candidate by default.
4. **Security posture.** Keep Dependabot alert monitoring on archived repos readable: alerts freeze but historic vulnerabilities remain queryable; decide whether archived-but-public critical CVEs warrant an exception (unarchive, patch, re-archive) — the default answer for libraries with downstream users is yes.
5. **Automation.** Drive the policy with a scheduled script (gh CLI or REST): list repos by pushed_at, notify owners, then archive via `gh api -X PATCH /repos/{org}/{repo} -f archived=true`. Log every action to the audit trail.

## Archive Program and Backups

1. **What the Archive Program is.** GitHub's partnership with the Internet Archive and the Arctic World Archive preserves public repository snapshots for the very long term. It is preservation, not availability — it does not restore a deleted repo on request.
2. **What it is not.** It covers public repos only; private repos have no such safety net. Losing org access or deleting a private repo without a mirror loses the content.
3. **Independent backup remains mandatory.** Mirror clones (or vendor backup tooling) on a schedule, stored outside GitHub. For the example project fleet this pairs with the audit-log-streaming and org-runbook practices already documented in this knowledge base.
4. **Forks as weak backup.** A fork preserves Git data but not Issues, Projects, releases metadata, or wiki — never accept a fork as an archive strategy for anything with discussion history.

## Pitfalls

1. **Archive-as-deletion confusion.** People archive a repo expecting it to disappear from search and pickers entirely; it remains fully visible until you also change the description, rename with a tombstone prefix, or move it to an archive org.
2. **Unarchive surprises.** Unarchiving re-enables scheduled workflows and stale webhooks that immediately fire; disable them before the first unarchive merge.
3. **Frozen Pages.** An archived repo's GitHub Pages site keeps serving its last deploy indefinitely — a commonly forgotten live surface with old content.
4. **Transfer lock.** Discovering you cannot transfer an archived repo during an org migration forces a rushed unarchive; handle transfers before archiving whenever the org structure is in motion.
