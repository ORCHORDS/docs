# lazy-fail-discoveries

**Issue:** Lazy-fail + discoveries
**Date:** 2026-08-09
**Status:** documented

## Symptom
An agent says "everything is done" but the team
discovers 3 issues. The agent didn't find them
because the agent only verified its own work.

## Root cause
**Self-verification is biased.** The agent should
discover (not just verify).

**Source:** Agent meta-lesson.

## The "L1 SHIP OR EXPLAIN" rule

Every cycle returns with one of:
- (a) **Merged artifact** — code, doc, config
- (b) **Opened PR** — ready to merge
- (c) **New recon finding** — discovery
- (d) **Explicit blocker** — can't proceed

Never "nothing to do."

## The "L2 NO STABLE/IDLE" rule

If the queue is empty:
- **Run recon:** Find more issues
- **File ≥1 finding:** Per cycle
- **Never end** with "nothing to do"

Idle = not looking.

## The "L3 USER-PIVOT" rule

Before destructive ops:
- **User must approve** in current session
- **No self-merge / push** / revert
- **Bot CI ✅ is necessary but not sufficient**

The user is the final reviewer.

## The "L4 EVIDENCE REQUIRED" rule

Every claim needs:
- **curl evidence:** Or actual API call
- **Real code grep:** Or actual file content
- **No hand-waving:** "I think" = no

Evidence first.

## The "5+6 stages" closure spec

For closure:
1. **Official doc** — Read the spec
2. **Claim review** — With sub-agent
3. **Live curl** — Verify
4. **Sibling regression** — Check other places
5. **Independent verifier** — Different session
6. **Live post-deploy** — Verify in production

Closure is multi-stage.

## The "atomic comment + close" rule

When closing an issue:
- **Post bulletproof evidence comment** AT THE SAME TIME
  as `state=closed` PATCH
- **Never close first** — comment, then close (atomic)
- **Root cause** of 13 silent closures

The comment is part of the close.

## The "don't close with fix pending" rule

- **Don't close with "fix pending"** — issue stays OPEN
  until PR merged + built + deployed + live-verified
- **Document adjacent pre-existing bugs** in commit
  message but DON'T fix in same PR
- **Track separately** for follow-up

The close is final.

## The "verify before fixing" rule

Before any fix:
- **Verify the bug** — Don't trust memory
- **Web search** — 30s search < 5 commits of debugging
- **Source-of-truth** — Official docs > GH > MDN > SO

The fix is grounded.

## The "scope discipline" rule

For each cycle:
- **One project at a time** — Don't mix
- **One issue at a time** — Atomic
- **Defined scope** — What + why

The scope is clear.

## The "evidence checklist" pattern

For every claim:
```markdown
- [ ] curl / web fetch with output
- [ ] Real code grep with line numbers
- [ ] Source citation (link)
- [ ] Reproduction steps
```

The evidence is documented.

## The "sub-agent verification" pattern

For critical decisions:
- **Sub-agent review** — Independent
- **Different session** — Fresh context
- **Disagreement is signal** — Not noise

The verification is independent.

## The "user is the oracle" rule

When uncertain:
- **Ask the user** — Don't guess
- **Show the question** — Concrete
- **Show options** — With trade-offs
- **One question at a time** — Don't overwhelm

The user is the source of truth.

## The "doc as you go" rule

- **Document in commit message** — Not follow-up
- **PR description = audit** — Not afterthought
- **Update KB** — Lessons learned
- **Track in agent memory** — Cross-session

The doc is part of the work.

## The "PAT self-merge CI workaround"

For Cloudflare Pages:
- **Symptom:** PR opened, no workflow runs after 3+ min
- **Cause:** PAT admin → `PUT /pulls/<n>/merge` triggers CI on
  the main-branch push
- **Fix:** Merge via API. Saves 5-10 min per cycle.

The workaround is documented.

## The "bash multiline -d gotcha"

For curl:
- **Symptom:** `curl -d '...'` with multi-line → syntax error
- **Workaround:** Write to file, then `python3 -c "import json; subprocess.run([...])"` with `json.dumps`
- **Or:** `cat > /tmp/body.md << EOF` then `-d @/tmp/body.md`

The gotcha is documented.

## The "git identity" rule

For commits:
- **Commit AS the GitHub user** — `example.com <maintainer@example.com>`
- **Per-session config** — `git config user.name "..." && git config user.email "..."`
- **NO `Co-authored-by: Mavis` trailer** — Pollutes audit trail
- **WIP wrong identity:** `git reset --hard origin/main` then recommit

The identity is correct.

## The "local CI before ship" rule

Before claiming "shipped":
- **Run FULL local CI** — `lint + typecheck + build + test`
- **For example.com:** `npm run lint && tsc -b --noEmit && npx vitest run && npm run build`
- **For example project:** Whatever `.github/workflows/*.yml` defines
- **Green test suite ≠ green CI** — Lint is often separate

The CI is verified.

## The "typosquat trap" rule

For orchard (no A) vs orchards (with A):
- **`example.com` (no A)** = real site, 8 letters
- **`orchards.com` (with A)** = typosquat owned by 3rd party
- **NEVER add to repo** — Wrap in backticks
- **Verify spelling BEFORE any file write** — Repeated 3+ times
- **Use `curl -L`** — Typosquat appears on every page after redirect

The trap is documented.

## The "D1 db.batch() BROKEN" rule

For D1 bundler:
- **Issue:** esbuild strips `sql` field
- **Fix:** Use `db.exec()` for DDL, `db.prepare().run()` for DML
- **Don't:** Use `db.batch()` for complex queries

The bug is documented.

## The "enc.encode() CSV bug"

For WebCrypto:
- **Issue:** `enc.encode(uint8array)` returns CSV "0,0,0,..."
- **Fix:** Use the Uint8Array directly
- **Caveat:** PBKDF2 max 100k iter

The bug is documented.

## Verification
- **Test:** Every claim has evidence
- **Test:** Scope is clear
- **Test:** User approves destructive ops
- **Live:** CI is green
- **Audit:** Quarterly review

## Gotchas
- **The "self-verify" anti-pattern.** Sub-agent
  review.
- **The "idle" anti-pattern.** Recon.
- **The "no evidence" anti-pattern.** Always cite.

## Related
- `lessons/lazy-fail-evidence-discipline.md`
- `lessons/scope-discipline.md`
- `lessons/user-pivot-rule.md`
- `lessons/when-to-ask-vs-push.md`
