# .gitattributes Merge Drivers and Filters

Date: 2026-08-17
Author: the platform team
Status: published

## Symptom

Merges produce conflicts in generated lockfiles or auto-generated
source files that could be resolved trivially, or Windows
contributors introduce CRLF line endings that break shell scripts
and CI linters.

## Context

`.gitattributes` attaches metadata to path patterns, telling Git
how to handle line endings, diffs, merges, and archives. Custom
merge drivers replace Git's conflict-marking algorithm with your
own script for specific file types. Rules in the most specific
matching pattern win; ordering matters less than specificity.

## text=auto Line Endings

```gitattributes
# Normalize to LF in the repo; check out as-is on each OS
* text=auto eol=lf

# Force LF even on Windows checkout
*.sh     text eol=lf
Makefile text eol=lf

# Always CRLF
*.bat    text eol=crlf
*.cmd    text eol=crlf

# Binary — never touch
*.png   binary
*.wasm  binary
```

After adding or changing line-ending rules:
`git add --renormalize . && git commit -m "chore: renormalize"`

## merge=union for Lockfiles

The `union` driver concatenates both sides without conflict
markers — safe only when duplicates are harmless:

```gitattributes
.gitignore  merge=union
```

For `pnpm-lock.yaml` and `package-lock.json`, duplicates
corrupt the lockfile. Use a custom "keep ours" driver instead:

```gitattributes
pnpm-lock.yaml    merge=driver-lockfile
package-lock.json merge=driver-lockfile
yarn.lock         merge=driver-lockfile
```

Register in `.git/config` (or team setup script):

```ini
[merge "driver-lockfile"]
  name   = Keep ours; regenerate after merge
  driver = lockfile-merge %O %A %B %L %P
```

```bash
#!/usr/bin/env bash  # lockfile-merge — on $PATH
cp "$2" "$2.resolved" && mv "$2.resolved" "$2"
exit 0   # 0 = resolved; CI runs install to regenerate
```

## Custom Merge Driver for Generated Files

Accept either side for protobuf or GraphQL generated output;
codegen rebuilds on the next `build` step:

```gitattributes
src/generated/**  merge=ours
```

```ini
[merge "ours"]
  name   = Keep our generated files
  driver = true   # always exits 0, keeping %A (ours)
```

## linguist-* for GitHub Language Stats

```gitattributes
vendor/**          linguist-vendored=true
src/generated/**   linguist-generated=true
*.md               linguist-documentation=true
docs/**            linguist-documentation=true
workers/src/*.ts   linguist-language=TypeScript
```

These attributes are read only by GitHub's Linguist library;
they have no effect on local Git behaviour.

## export-ignore for Archive Builds

```gitattributes
.github/**   export-ignore
tests/**     export-ignore
*.test.ts    export-ignore
docs/**      export-ignore
```

Build a clean release tarball:

```bash
git archive --format=tar.gz \
  --prefix=myproject-1.2.3/ \
  v1.2.3 | gzip > myproject-1.2.3.tar.gz
```

## Git LFS Pointer Files

```gitattributes
*.psd              filter=lfs diff=lfs merge=lfs -text
*.mp4              filter=lfs diff=lfs merge=lfs -text
design/exports/**  filter=lfs diff=lfs merge=lfs -text
```

`-text` disables line-ending normalization. The LFS client
stores real files in `.git/lfs/objects` and replaces them with
small pointer files in the working tree.

## Anti-patterns

- `merge=union` on lockfiles — produces invalid lockfiles with
  duplicate or conflicting dependency entries.
- Relying on `core.autocrlf` without `.gitattributes`; the
  setting is per-developer machine and will vary.
- Defining merge drivers only in `.git/config` without a team
  setup script; new clones inherit none of them.

## Gotchas

- `export-ignore` is silently ignored by `git bundle` —
  it only affects `git archive`.
- `linguist-generated` suppresses GitHub diffs and syntax
  highlighting, which is usually desirable but surprises
  reviewers who expect to see the diff.
- Merge drivers in `.git/config` are not committed to the repo;
  distribute them via a `make setup` or `script/bootstrap`.

## Verification

```bash
# Show effective attributes for a file
git check-attr -a src/generated/types.ts

# List files with a non-default merge strategy
git ls-files | xargs git check-attr merge | \
  grep -v ': merge: unset'

# Confirm archive exclusion
git archive HEAD | tar -t | grep -v '.github'

# Check LFS tracking
git lfs ls-files
```

## Related

- /documentation/categories/worktree/git-lfs-2026.md
- /documentation/categories/worktree/git-hooks-2026.md
- /documentation/categories/worktree/git-conflict-resolution-2026.md
- /documentation/categories/worktree/monorepo-pnpm-turborepo-2026.md

## Source URLs (verified 2026-08-17)

- https://git-scm.com/docs/gitattributes
- https://git-lfs.com/
- https://docs.github.com/en/repositories/working-with-files/managing-files/customizing-how-changed-files-appear-on-github
- https://www.git-scm.com/docs/git-archive
- https://github.com/github/linguist/blob/master/docs/overrides.md
