# Git Blame and Code Archaeology Workflows

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

You are staring at a 12-line function and have no idea why it exists, why it does
what it does, or whether it is safe to touch. The function has no comment, the
variable names are opaque, and your colleague who wrote it left the team.

Or you have a production bug and need to find the exact commit that introduced it
without running `git bisect` because you have no reliable test to automate the
reproduction.

Code archaeology is the practice of using source-control history as documentation
— reconstructing intent, tracing decision trails, and locating the origin of
behavior from nothing but commits, blame annotations, and log messages.

---

## Context

Every commit records four pieces of information that archaeology exploits: *what*
changed (the diff), *when* it changed (author/committer timestamps), *who* changed
it (author identity), and *why* it changed (the commit message). The skill is
assembling these fragments into a coherent story.

Tools in the archaeology toolkit:

| Tool | Best for |
|---|---|
| `git blame` | Line-by-line authorship and timestamp for a single file |
| `git log -S` | Find commits that added or removed a specific string (pickaxe) |
| `git log -G` | Find commits whose diff matches a regex |
| `git log --follow` | Track a file across renames |
| `git log -L` | Trace a function or line range across history |
| `git show` | Inspect the full context of a single commit |
| `git log --all --source` | Search across all branches and tags |

---

## Core Technique 1 — git blame with Context

### Basic blame

```bash
# Show who last touched each line of a file
git blame src/payments/processor.ts

# Show blame with line numbers and short commit hashes
git blame -s src/payments/processor.ts

# Ignore whitespace-only changes (crucial: reformatting hides real authors)
git blame -w src/payments/processor.ts

# Ignore specific commits (e.g., a mass reformatter run)
# First, create a .git-blame-ignore-revs file:
echo "a3f7c1d92e8b4f56a1c2d3e4f5a6b7c8d9e0f1a2  # prettier reformatting 2025-03" \
  >> .git-blame-ignore-revs

# Then blame with that file:
git blame --ignore-revs-file .git-blame-ignore-revs src/payments/processor.ts

# Configure it project-wide so all blame commands use it automatically:
# In .gitconfig or repository config:
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Committing `.git-blame-ignore-revs` to the repository means every teammate gets
the same "clean" blame view for free — it becomes part of the project contract.

### Blame a specific past version

```bash
# Blame the file as it existed two releases ago
git blame v2.3.0 -- src/payments/processor.ts

# Blame the file at a specific commit
git blame a3f7c1d -- src/payments/processor.ts

# Blame only a range of lines (lines 40 to 70)
git blame -L 40,70 src/payments/processor.ts
```

---

## Core Technique 2 — Pickaxe Search (git log -S and -G)

The pickaxe is the most powerful archaeology tool. It finds the exact commit that
introduced or removed a string, even across renames and rewrites.

```bash
# Find every commit that added or removed the string "PAYMENT_TIMEOUT"
git log -S "PAYMENT_TIMEOUT" --all --oneline

# Find commits whose diff patch matches a regex (more flexible than -S)
git log -G "retry.*attempt|attempt.*retry" --all --oneline --source

# Show the full diff of each matching commit (instead of just the hash)
git log -S "PAYMENT_TIMEOUT" --all -p

# Restrict to a specific file or directory
git log -S "PAYMENT_TIMEOUT" -- src/payments/

# Restrict to a date range
git log -S "PAYMENT_TIMEOUT" --after="2025-01-01" --before="2025-06-01"

# Find the commit that first ADDED a symbol (look for + lines)
git log -S "export function processPayment" --diff-filter=A --all -p
```

`-S` detects commits where the count of occurrences of the string changes (i.e.,
the commit added or removed instances). `-G` detects commits where the diff text
matches the regex, even if the occurrence count stays the same.

---

## Core Technique 3 — Line-History Tracing (git log -L)

`git log -L` traces the complete history of a function or line range across all
renames and rewrites. It is the deep-dive tool once `blame` has identified the area.

```bash
# Trace the history of lines 40 to 70 in a file
git log -L 40,70:src/payments/processor.ts

# Trace a named function (git uses ctags-style heuristics)
git log -L ':processPayment:src/payments/processor.ts'

# Same but show the diff of each change
git log -L ':processPayment:src/payments/processor.ts' -p

# Trace across renames (git follows the rename chain automatically)
git log -L ':processPayment:src/payments/processor.ts' --follow
```

The output reads chronologically in reverse — newest change first — and shows
exactly what the function looked like before and after each commit that touched it.

---

## Core Technique 4 — File History Across Renames

```bash
# Follow a file's history even through renames
git log --follow --oneline -- src/payments/processor.ts

# Show the full diff at each step, including the rename event itself
git log --follow -p -- src/payments/processor.ts

# Find when and why a file was renamed
git log --follow --diff-filter=R --summary -- src/payments/processor.ts

# Find all files renamed in a commit
git show --stat --diff-filter=R a3f7c1d
```

Without `--follow`, history stops at the most recent rename. For files that have
been moved across directories or renamed as part of refactors, `--follow` is
mandatory for complete archaeology.

---

## Structured Investigation Workflow

When facing an unknown piece of code, run these steps in order:

```bash
# Step 1: identify the last-touching commits for the suspicious region
git blame -w --ignore-revs-file .git-blame-ignore-revs \
  -L 40,70 src/payments/processor.ts

# Step 2: read the full context of the top blame commit
COMMIT=$(git blame -w -L 40,70 src/payments/processor.ts | \
  awk '{print $1}' | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
git show "$COMMIT"

# Step 3: read the PR/merge that contains this commit (GitHub CLI)
gh api "/repos/org/repo/commits/$COMMIT/pulls" \
  --jq '.[0] | {number, title, body, merged_at}'

# Step 4: if the commit message or PR is thin, search for the issue reference
# (GitHub links commits to issues via "Fixes #NNN" or "Closes #NNN")
gh issue view $(git log "$COMMIT" -1 --pretty="%B" | grep -oP '#\K[0-9]+' | head -1)

# Step 5: find related commits in the same time window
git log --oneline --after="$(git show -s --format=%ci $COMMIT)~1day" \
        --before="$(git show -s --format=%ci $COMMIT)~-1day" -- .

# Step 6: check if a refactoring commit obscures the real author
git log -S "$(git show $COMMIT | grep '^+' | tail -3 | awk '{print $2}' | head -1)" \
  --all --oneline -- src/payments/
```

---

## Anti-patterns

**Blaming `HEAD` without ignoring reformatter commits.** Running bare `git blame`
on a file that went through a Prettier/Black/gofmt mass-reformat commit will show
the formatter as the author of every line. Always maintain `.git-blame-ignore-revs`.

**Stopping at the first blame result.** The most recent touching commit is not
always the *interesting* commit. The function may have been refactored dozens of
times. Keep digging with `git log -L` to find the original creation.

**Ignoring the PR body and linked issues.** Commit messages are often thin.
The PR description, linked issue, and Slack thread referenced in the issue are
where the decision rationale lives. Always chase the PR and issue trail.

**Using archaeology to assign blame culturally.** Blame in `git blame` is
authorship metadata, not accountability for bugs. The author of a line may have
been working under constraints set by someone else. Blameless culture applies to
code archaeology too.

**Trusting committer identity without verified signatures.** On repositories that
do not enforce signed commits, the `author` field can be anything. On repos with
unsigned history, correlate with PR authorship (which GitHub authenticates) rather
than commit author.

---

## Gotchas

- `git log -L` with a function name heuristic (`-L ':functionName:file'`) relies on
  language-aware heuristics that work well for C, Python, and Ruby but can misfire
  for TypeScript, Go, and Rust depending on git version. Fall back to explicit line
  ranges when the function heuristic produces unexpected results.

- `git blame -w` ignores whitespace in the diff, not in the blame output. Lines that
  differ only in indentation will still show the reformatter as the author of surrounding
  non-whitespace lines if the reformatter also changed those lines.

- The pickaxe (`-S`) is case-sensitive by default. Add `-i` to `git log` for
  case-insensitive pickaxe: `git log -S "paymenttimeout" -i`.

- `--follow` for renames only works for single-file paths. You cannot use it with
  directory paths.

- `git log --all` includes refs from remote branches that have been pruned locally.
  Run `git fetch --prune` before an archaeology session to get a fresh remote picture.

---

## Verification

```bash
# Verify .git-blame-ignore-revs is respected
git config blame.ignoreRevsFile
# should print: .git-blame-ignore-revs

# Confirm a known reformatter commit is in the ignore file
grep "$(git log --oneline | grep -i 'prettier\|format\|reformat' | head -1 | awk '{print $1}')" \
  .git-blame-ignore-revs

# Test pickaxe on a known string
git log -S "function processPayment" --all --oneline -- src/payments/
# should show the commit that originally defined the function

# Validate follow works across a known rename
git log --follow --oneline -- src/payments/processor.ts | tail -5
# last entries should predate the rename and show the old filename
```

---

## Related

- `git-bisect-automation.md` — when you need to find the introducing commit by
  reproducing a bug, not by reading diffs
- `git-hooks-2026.md` — pre-commit hooks that enforce commit message quality,
  making archaeology easier via richer messages
- `conventional-commits-2026.md` — structured commit messages that archaeology
  can parse programmatically
- `blameless-culture-implementation.md` — cultural context for using blame data
  without assigning personal blame

---

## Sources

- `git blame` man page: https://git-scm.com/docs/git-blame
- `git log` man page (pickaxe, -L, --follow): https://git-scm.com/docs/git-log
- "Git Internals" by Scott Chacon: https://git-scm.com/book/en/v2
- GitHub ignoreRevsFile support: https://docs.github.com/en/repositories/working-with-files/using-files/viewing-a-file#ignore-commits-in-the-blame-view
