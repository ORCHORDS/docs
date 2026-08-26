# git-lfs-github-management

**Issue:** Design assets, model weights, and installer binaries live in the repo via Git LFS. Everything works until the monthly bill alert lands: the 1 GB free bandwidth quota evaporated by week two, CI is the top consumer (every `actions/checkout` with LFS pulls all objects, and GitHub counts every LFS download against quota — including CI), new pushes fail on the 2 GB per-file ceiling, and "we deleted the big files" freed no storage because LFS storage never shrinks retroactively. Managing LFS on GitHub is a quotas-plus-hygiene problem, not just an `lfs track` problem.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Limits and billing mechanics

1. **Free quota is per-account: 1 GB storage, 1 GB/month bandwidth.** Bandwidth resets monthly; storage does not shrink when files are deleted — every LFS object ever uploaded keeps counting until history is rewritten or packs are adjusted. Check usage under Settings → Billing → Git LFS.
2. **Data packs are the paid unit.** Each data pack adds ~50 GB storage + 50 GB bandwidth per month (~$5), bought at account/org level. Budget from measured usage, not guesses: one CI job pulling a 3 GB assets directory ten times a day is ~900 GB/month.
3. **Hard file-size ceilings.** Files over 100 MB cannot be pushed as plain git objects (must be LFS or rejected outright); GitHub caps LFS objects at 2 GB per file, and repositories are recommended to stay under 5 GB total including LFS — treat these as architectural limits, not tuning knobs.
4. **CI downloads count.** GitHub staff have confirmed every LFS download counts against quota, including `actions/checkout`. The default `actions/checkout` behavior (`lfs: false` in v4+) skips LFS objects at checkout — older configs and explicit `lfs: true` re-download everything on every run.
5. **Quota exhaustion blocks everyone.** When bandwidth/storage runs out, LFS pulls fail for all collaborators until packs are added or the month rolls over — monitor it like a production dependency.

## Setup and tracking hygiene

1. **Track before committing.** `git lfs install` once per clone; `git lfs track "*.psd" "assets/**"` writes `.gitattributes`; commit `.gitattributes` first — files committed before tracking are plain blobs and stay bloated in history until migrated.
2. **Prefer extensions over broad globs.** Track by extension (`*.png`, `*.onnx`) or narrow directories; `*` or repo-wide patterns drag throwaway artifacts into paid storage.
3. **Pre-push safety.** `git lfs status` before pushing catches accidentally-staged large files; a pre-push hook (`git lfs pre-push` is installed automatically) fails fast instead of after a 900 MB upload.
4. **Inspect what's stored.** `git lfs ls-files` lists tracked objects and sizes; use it in CI (on a schedule) to alert when the tracked set grows past a threshold — catching a 400 MB dataset commit at PR time is cheap, after merge it's quota.
5. **Server-side availability.** GitHub's LFS service needs no separate endpoint config, but self-hosted or external LFS (e.g., S3-backed) exists as an escape hatch when GitHub quotas don't fit (custom `lfs.url` in `.lfsconfig`).

## CI patterns that don't burn quota

1. **Default `lfs: false`, pull selectively.** Leave checkout's LFS off; in jobs that need assets, `git lfs pull --include="assets/fonts/**"` fetches only what that job needs. Jobs that don't touch binaries fetch zero LFS bytes.
2. **Cache LFS objects.** `actions/cache` on `.git/lfs` (keyed by a hash of `.gitattributes` or the LFS pointer set) reuses objects across runs — for matrix builds (5 jobs × same assets) this divides bandwidth by the fan-out.
3. **Nightly, not per-PR, for heavy assets.** Full-asset verification jobs can run on a schedule and on path-filters (`assets/**`), so docs-only PRs cost nothing.
4. **Push with LFS from CI.** Release jobs that build and push binaries via LFS need `lfs: true` checkout plus a PAT/App token with LFS write — scope these jobs narrowly since they are both quota- and credential-sensitive.
5. **Measure before and after.** Compare a week of billing telemetry after switching to selective pull + caching; the bandwidth graph under Billing is the acceptance test, not perceived build speed.

## History rewrite and reduction

1. **`git lfs migrate import`.** Converts existing large blobs in history into LFS pointers: `git lfs migrate import --include="*.zip" --everything` rewrites every branch/tag. This shrinks future clones and is the only way to move already-committed files into LFS.
2. **Rewrite is a force-push event.** `migrate` changes commit SHAs repo-wide: coordinate, announce, force-push all refs, and have collaborators re-clone. Open PRs need rebasing; external forks diverge.
3. **Storage does not auto-shrink.** Removing files now only stops future growth; reducing billed storage requires rewriting history (migrate, or `git filter-repo` to strip paths entirely) and asking GitHub Support to run garbage collection on the repo afterwards.
4. **Do not mix LFS and non-LFS copies.** After migration, stale clones with the old plain blobs can "work" offline and mislead — a post-migration re-clone mandate avoids duplicate histories.
5. **Alternatives when LFS is the wrong tool.** Release-asset binaries belong in GitHub Releases (free, CDN-backed); deduplicated artifacts belong in Actions artifacts or external object storage with a fetch script. LFS is for files the working tree genuinely needs at specific commits.

## Related

1. **`github-actions-cache-dependencies.md`.** Cache keying patterns reused for `.git/lfs`.
2. **`github-actions-docker-build-push.md`.** Layer binaries without polluting LFS quotas.
3. **`github-api-rate-limiting.md`.** Same discipline: quotas need monitoring, not hoping.
