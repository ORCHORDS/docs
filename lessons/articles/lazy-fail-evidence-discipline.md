# lazy-fail-evidence-discipline

**Issue:** Silent acceptance of unverified work
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main (also applies to a sibling repo)
**Author:** the platform team
**Status:** documented (rule, not bug)

## The rule

Every cycle returns with **one** of:
- **(a) merged artifact** (commit on main + PR closed)
- **(b) opened PR** (work shipped to the platform, awaiting review)
- **(c) new recon finding** (something the user should know about)
- **(d) explicit blocker** (with what would unblock it)

**No "nothing to do" exits. No idle. No drift.**

## The evidence rule

Every claim has curl evidence or real code grep. No "I think",
"probably", "this should work". If you can't cite a source, you
can't make the claim.

## What "silent acceptance" looks like

These are all the same bug:
- "I deployed it, looks fine" (without curl)
- "Tests pass, should be good" (without lint + typecheck + build)
- "I added the import" (without grep showing it's used)
- "I think NOWPayments returns X" (without checking the docs)
- "This is probably how D1 batch works" (without reading the source)
- 5 commits of debugging on a wrong assumption
- "Should be fixed in the next deploy" (without live verify)

The pattern: confidence without evidence.

## The fix

### 1. Ship or explain
Every turn produces an artifact. If you can't ship, you explain
why. The user can decide if the reason is good enough.

### 2. No stable/idle
If the queue is empty, you run recon and file ≥ 1 new finding.
You do not end the turn with "nothing to do." Even if the only
thing to file is "the doc has a typo", that's a finding.

### 3. User-pivot before destructive ops
You do NOT:
- Self-merge to main
- Force-push to main
- Delete branches
- Revert commits
- Push to a PR the user hasn't reviewed

Even with bot CI green. Even with admin PAT. Even if "the fix
is obvious." Wait for the user to say "ship it" / "merge it" /
"proceed."

### 4. Evidence required, every claim
```ts
// ❌ BAD
// I think NOWPayments returns the IPN callback as JSON
async function handleIPN(req: Request) {
  const body = await req.json();  // might be form-encoded!
  // ...
}

// ✅ GOOD
// NOWPayments IPN spec: POST with Content-Type: application/json
// https://nowpayments.io/payment-tools/ipn
// Verified 2026-08-09: they send JSON. (No form-encoded variant.)
async function handleIPN(req: Request) {
  const body = await req.json();
  // ...
}
```

### 5. Verify before fixing
30 seconds of web search > 5 commits of debugging on a wrong
assumption. ALWAYS verify the vendor API contract before writing
code against it.

Source-of-truth order:
1. Official vendor docs
2. GH issues/Discussions/changelog
3. GH source code when docs are vague
4. MDN/WHATWG/IETF
5. SO/Reddit/Discord (verify against official)
6. Vendor blog

### 6. Cite in three places
- **Commit message:** "Link: <vendor doc URL>" at the bottom
- **PR description:** 1-2 source links in the body
- **Code comment:** one-line cost (e.g. "PBKDF2 capped at 100k in
  workerd — see W3C spec footnote 7")

## Anti-patterns

| Situation | Don't | Do |
|---|---|---|
| Vendor API unknown | "I think X returns Y" | `curl -s X | jq` then read docs |
| Same bug twice | Reinvent the fix | `grep` the KB for the symptom |
| Tests pass | "Shipped!" | Run lint + typecheck + build too |
| Bug in 3+ files | Sed blindly | Read each file's context first |
| Worktree accidentally committed as gitlink | Push and hope | `git rm --cached`, fix on a new branch |
| Token in chat | Keep using it | Rotate NOW, treat as compromised |
| Co-authored-by trailer | Add it | NEVER. Owner is sole author. |

## Why this matters

The KB is built on this discipline. Every entry in
`documentation/` was written AFTER live verification or
authoritative source citation. An unverified entry is worse than
no entry — it teaches the next agent a wrong lesson.

## Related
- the platform issue: (none — this is a process rule, not a code issue)
- The "self-improving-agent" project: this rule is the project's
  own loop
- memory topic: `orchords-the platform-i18n-20locales` — every PR there
  has a 24-point compliance audit
