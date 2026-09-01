# Repository-Wide EOL Normalization and Custom Merge Driver Governance

## Scope

This article covers the rollout and enforcement of line-ending policy through `.gitattributes`, and the governance of custom merge drivers declared alongside it: how to migrate a repository with mixed CRLF and LF content without producing phantom whole-file diffs, how to write and distribute a custom low-level merge driver, and how to keep both from silently degrading. It applies to repositories with contributors on mixed operating systems and to repos absorbing imported history. It does not cover Linguist statistics attributes, `export-ignore` archive trimming, or Git LFS filter setup, which are separate attribute concerns.

## Workflow or implementation guidance

EOL chaos is a repository property, not a machine property. The single most important move is to stop relying on `core.autocrlf`, which is a per-clone configuration value that differs across contributor machines, and to declare policy centrally in a committed `.gitattributes` file, which every clone reads identically.

**Step 1 — Inventory before you legislate.** Find which files actually have CRLF bytes in the index versus the working tree. `git ls-files --eol` prints, per file, `i/lf w/crlf` style pairs: `i/` is what is stored, `w/` is what is on disk. A file showing `i/crlf` is stored with CRLF in the object database and will fight every normalization rule you add. Run `git ls-files --eol | grep -c 'i/crlf'` to count the scope of the problem before announcing a migration date; if the count is four figures, the renormalization commit will be large and needs coordination, not a Friday afternoon.

**Step 2 — Declare the policy with a minimal attribute set.** The recommended shape normalizes all text to LF in the repository while forcing the handful of platform-specific formats to CRLF and protecting binaries from any conversion:

```gitattributes
* text=auto eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.ps1 text eol=crlf
*.png binary
*.woff2 binary
```

The subtlety of `text=auto` is that Git guesses which files are text; anything it misclassifies as text (rare binary formats that happen to contain no NUL byte in the first 8,000 bytes) can be corrupted by normalization, which is why binaries are explicitly marked `binary` rather than left to the heuristic. The `binary` attribute is shorthand that unsets text conversion, diff, and merge behavior at once.

**Step 3 — Renormalize in a dedicated commit.** After writing the attributes, run `git add --renormalize .` — this re-stages every file as if freshly added under the new rules, converting index contents to LF. Commit this alone, with no other changes in the diff, and label it clearly (for example `chore: normalize line endings to LF`). Mixing renormalization with functional changes is how you manufacture a commit that can never be reviewed. Note that `.gitattributes` applies at commit time from the tip, so files committed before the policy existed keep their stored CRLF until renormalized — the attribute file is not retroactive.

**Step 4 — Suppress the blast radius on blame.** The renormalization commit touches every stored-CRLF file, so `git blame` will point all those lines at the migration. Register the renormalization commit in `.git-blame-ignore-revs` and reference that file from the attributes:

```gitattributes
.git-blame-ignore-revs ignore
```

Contributors then run `git config blame.ignoreRevsFile .git-blame-ignore-revs` once (scripted in bootstrap), and blame again shows the true last-content-change author.

**Step 5 — Custom merge drivers: define, distribute, verify.** A custom driver takes over conflict resolution for matched paths. Git invokes the configured command with `%O` (base), `%A` (ours), `%B` (theirs), `%L` (conflict-marker size), `%P` (path) and expects exit code zero to accept the (possibly rewritten) `%A` file as the resolution. A driver that keeps ours and lets regeneration fix the rest is one line:

```ini
[merge "ours-regen"]
    name = keep ours, regenerate in CI
    driver = true
```

The critical governance gap: the driver definition lives in `.git/config` or a shared include, not in the repository, while the attribute referencing it does live in the repository. A fresh clone that matches `pnpm-lock.yaml merge=ours-regen` but lacks the config entry falls back to the normal merge machinery — not an error, just different behavior. Distribute the config through a bootstrap script or `git config --local include.path ../.gitconfig` pattern, and make CI deliberately fail when a path declares an unknown driver. A CI probe can run `git ls-files | xargs git check-attr merge` and assert every non-`unset` value has a corresponding `merge.<name>.driver` key, catching the fresh-clone gap in automation rather than in a bad merge.

## Controls

- EOL policy lives in `.gitattributes`; `core.autocrlf` is never the team's answer because it is machine-scoped.
- The renormalization commit contains only renormalization; functional changes ride separately.
- The renormalization commit SHA is recorded in `.git-blame-ignore-revs` so blame stays truthful.
- Binaries are explicitly marked `binary`; nothing relies on `text=auto` classification for non-text formats.
- Custom merge drivers are distributed by a committed bootstrap script; CI asserts every referenced driver name resolves to a configured command.
- Changes to the attributes file themselves require review by someone other than the author, because attribute edits are repo-wide policy edits.

## Validation evidence

- `git ls-files --eol` shows `i/lf` for every text file after migration; the count of `i/crlf` entries is zero outside the forced-CRLF patterns.
- `git check-attr text eol -- <path>` returns the intended attributes for spot-checked paths, including negatives (binaries show `text: unset`).
- A synthetic merge on a scratch branch — two branches each touching a driver-matched file — resolves without conflict markers and produces the driver's declared behavior, proving the driver is installed, not just referenced.
- A fresh clone followed by the bootstrap script reproduces identical `git check-attr -a` output to a veteran clone, which is the drift test for driver distribution.
- `git diff` on a file edited only in its working-tree line endings (no content change) shows no changes after `git add --renormalize`, confirming normalization round-trips.

## Failure modes and correction

- **Phantom whole-file diffs in review.** A contributor without the attributes (pre-migration fork, stashed file) commits CRLF, and the PR shows every line changed. Correction: rebase onto the normalized tip and re-stage with `git add --renormalize .`; the diff collapses to the real change.
- **Driver referenced but not installed.** Merge conflicts appear on files the team believed were auto-resolved. Correction: the CI probe that asserts driver names resolve to configured commands fails the offending PR until bootstrap is run or the definition is added.
- **Hand-merged generated lockfiles.** The driver keeps ours, but someone resolves markers by editing the lockfile text directly. Correction: run the package manager's frozen install to regenerate, and treat a lockfile diff that is not machine-shaped as a review block.
- **Renormalization mixed with features.** A commit converts endings and changes logic in one diff, becoming unreviewable and unrevertable. Correction: split via interactive rebase before merge; policy states the renormalization commit is single-purpose.
- **Autocrlf fighting attributes.** A machine with `core.autocrlf=true` shows perpetual modification noise after migration. Correction: unset the local override (`git config --unset core.autocrlf`); the attributes are now the sole authority.
- **Heuristic misclassification corrupts a binary.** Correction: explicit `binary` marking for every non-text asset type in the repo; recovery is from history if a corrupted object was already pushed.

## Limitations

Normalization cannot rewrite already-published history; object-database CRLF from before the migration persists in old commits, so `git log -p` on pre-migration history still shows CRLF bytes, and clones that never renormalize keep diverging working trees. The `text=auto` heuristic is content-sniffing, not format awareness, so exotic binaries need explicit listing forever. Custom merge drivers run with full user privileges as local commands, which makes them a supply-chain surface: a malicious repository can declare `merge=<name>` attributes, though Git only executes drivers defined in local config, not in the fetched repository — the residual risk is a contributor blindly installing bootstrap scripts. Finally, blame suppression via `.git-blame-ignore-revs` requires per-clone configuration to take effect, so it is a convention with pockets of non-adoption rather than an enforced guarantee.

## Canonical sources

- Git documentation — gitattributes (text/eol attributes, merge attribute, built-in drivers): https://git-scm.com/docs/gitattributes
- Pro Git, 2nd edition — Customizing Git: Git Attributes: https://git-scm.com/book/en/v2/Customizing-Git-Git-Attributes
- GitHub Docs — Configuring Git to handle line endings: https://docs.github.com/en/get-started/getting-started-with-git/configuring-git-to-handle-line-endings
- Git documentation — git-config (core.autocrlf scoping): https://git-scm.com/docs/git-config
