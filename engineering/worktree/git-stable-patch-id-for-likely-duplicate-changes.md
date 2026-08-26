# Git stable patch IDs for likely duplicate changes

**Issue:** Rebases and cherry-picks change commit IDs, making object identity insufficient for finding equivalent patches.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

`git patch-id --stable` computes a reasonably stable patch fingerprint that ignores line numbers, whitespace, and file-diff ordering. Use it to find likely duplicate changes, not as cryptographic proof or semantic equivalence.

## Controls and verification

- Choose stable, unstable, or verbatim mode explicitly.
- Do not mix databases produced by incompatible modes or old Git versions.
- Confirm suspected matches by reviewing content, metadata, and context.
- Exclude merge commits only under an explicit policy.
- Keep the source commit range and Git version with stored IDs.
- Test reordered diffs, whitespace-only changes, and substantively different patches.

## Sources

- [Git: git-patch-id](https://git-scm.com/docs/git-patch-id)
- [Git: git-cherry](https://git-scm.com/docs/git-cherry)
