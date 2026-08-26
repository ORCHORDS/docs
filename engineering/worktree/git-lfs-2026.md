# git-lfs-2026

**Issue:** A team trains a PyTorch model. The .pt weights file is 450MB. The team commits to GitHub. The push is rejected: "File exceeds 100MB limit." The team tries splitting, hits Git LFS quotas, ends up with HuggingFace + a download script in README.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

GitHub rejects files >100MB, warns at >50MB. Git itself handles large files but GitHub's API has hard limits. The 2026 default for AI model weights, datasets, and binary assets is Git LFS or external storage with explicit download.

## Root cause

Git is content-addressable; every clone pulls full history. A 500MB model binary bloats every clone. Git LFS replaces the binary with a small pointer file (text) in the repo and stores the actual file on a separate server. GitHub manages the LFS server.

## The GitHub file size limits

| Limit | Threshold | Behavior |
|---|---|---|
| Warning | 50MB | `git push` warns |
| Reject | 100MB | push rejected with GH001 error |

Git LFS raises the per-file limit to 2GB (Free/Pro), 4GB (Team), or 5GB (Enterprise Cloud).

## The 3 storage options for large files

| Option | Best for | Trade-off |
|---|---|---|
| Git LFS (GitHub-managed) | files <5GB, single-team access | free tier: 1GB storage + 1GB bandwidth; overage paid |
| External storage (HuggingFace, S3, OSS) | files >5GB, large datasets, public model distribution | needs download script; repo holds pointer or link |
| DVC (Data Version Control) | ML-specific dataset versioning, large file diffs | adds tooling layer |

The 2026 default for AI model weights: HuggingFace for distribution + Git LFS for in-repo training snapshots. DVC for dataset versioning.

## The Git LFS setup

```bash
# Install (one-time per machine)
brew install git-lfs  # or apt install git-lfs, scoop install git-lfs
git lfs install

# Track large file types per repo
git lfs track "*.pt"
git lfs track "*.safetensors"
git lfs track "*.bin"

# .gitattributes is auto-updated; commit it
git add .gitattributes
git commit -m "track large files with git lfs"

# Now commits push files via LFS
git add model.pt
git commit -m "add model weights"
git push origin main
```

The pointer file in the repo looks like:
```
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b89102a3f1261ac81fd5bcb5
size 84977953
```

Tiny text. Real file on LFS server.

## The cloning gotcha

The 3 cloning scenarios.

| Scenario | What you get |
|---|---|
| `git clone` without LFS installed | pointer files (text, 100 bytes each) — files unusable |
| `git clone` with LFS installed | real files downloaded automatically |
| `GIT_LFS_SKIP_SMUDGE=1 git clone` + `git lfs pull --include="X"` later | manual control, smallest download |

Document this in the README. Most "the model file is missing" issues are missing LFS install on the cloner.

## The 6 migration patterns

| Pattern | When to use | Command |
|---|---|---|
| Pre-existing large files in history | clean up before adding LFS | `git lfs migrate import --include="*.pt"` then force-push |
| Filter by path | pull only specific LFS objects | `git lfs pull --include="models/**/*.safetensors" --exclude="*"` |
| Disable recent fetch | avoid historical LFS | `git -c lfs.fetchrecent=false lfs pull` |
| Trace slow transfer | debug stuck downloads | `GIT_TRACE=1 GIT_CURL_VERBOSE=1 git lfs pull` |
| Prune cache | reclaim disk | `git lfs prune` |
| Partial clone + sparse-checkout | limit non-LFS too | `git clone --depth 1 --filter=blob:none --single-branch ...` |

The HuggingFace forum thread (2026) documents the "much larger than model" issue — `git lfs pull` can pull more than you expect.

## The cost reality

GitHub LFS free tier: 1GB storage + 1GB bandwidth/month. Overage is paid.

| Plan | Storage | Bandwidth | Cost |
|---|---|---|---|
| Free | 1GB | 1GB/month | $0 |
| Pro | 2GB | included | $4/user/month |
| Team | 4GB | included | $4/user/month |
| Enterprise Cloud | 5GB/file | unlimited | $21/user/month |

For AI teams with many model files: the 1GB free tier is consumed in days. Budget for paid LFS or external storage.

## The alternative: external storage + download script

For >5GB files, public model distribution, or budget constraints, external storage is the 2026 default.

```python
# download_model.py
import os
from huggingface_hub import snapshot_download

if not os.path.exists("./model"):
    snapshot_download(
        repo_id="myorg/mymodel",
        local_dir="./model",
        allow_patterns=["*.safetensors", "*.json"]
    )
```

The repo holds the script + README; the model lives on HuggingFace. Cloners run `pip install -r requirements.txt && python download_model.py`. Document in README.

## The 5 anti-patterns

1. **Committing >100MB without LFS.** Push rejected; the error is cryptic.
2. **HuggingFace + Git LFS duplication.** Pick one. LFS for in-repo, external for distribution.
3. **Forgetting to commit .gitattributes.** LFS tracking won't work without it.
4. **No README hint about LFS.** Cloners get pointer files; "the model is missing" reports.
5. **Tracking everything with LFS.** Small text files don't need LFS. Only track >1MB typically.

## The DVC alternative for datasets

DVC (Data Version Control) is git for data and models.

```bash
# Init
dvc init

# Track a dataset
dvc add data/train.csv
git add data/train.csv.dvc data/.gitignore
git commit -m "track training data"

# Push to remote storage (S3, GCS, Azure, SSH)
dvc remote add -d myremote s3://mybucket/dvc
dvc push
```

DVC stores .dvc files (small text) in git, real data in remote storage. Git diff, branch, merge all work on the metadata.

## The 2026 AI storage pattern

For most AI/ML projects, the layered pattern:

1. **Source code** — git
2. **Small models (<100MB) and configs** — git or LFS
3. **Large model weights (100MB-5GB)** — Git LFS or HuggingFace
4. **Very large models / datasets (>5GB)** — HuggingFace, S3, OSS, DVC
5. **Inference artifacts** — object storage (S3, R2, OSS)

Pick the right layer per asset type. Don't put a 4GB model in plain git.

## Verification

The tell that LFS / large file storage is real:

- `.gitattributes` is in the repo with LFS patterns
- README documents the LFS install / pull / download step
- The model weights are either in LFS or downloaded from external storage
- The repo's largest files are <100MB (or are LFS-tracked)
- Free tier usage is monitored; upgrade or external storage is in place

The tell it isn't:

- "The model is missing" issues
- GH001 errors on push
- 500MB binary files in the repo
- No README hint about LFS

## Gotchas

- **Pointer files need LFS to be useful.** Without `git lfs install` on the cloner, the file is unusable.
- **Force-push after migration** — `git lfs migrate import` rewrites history; the force-push is required.
- **The free tier is small.** 1GB / month; a 500MB model consumes half. Plan accordingly.
- **LFS bandwidth is metered.** A CI pipeline that clones the full LFS history every run eats bandwidth.
- **HuggingFace is the de facto standard for AI model distribution.** Use it for public models; the in-repo size limits are not a HuggingFace problem.

## Related

- `worktree/sbom-slsa-2026.md` — supply chain for binaries
- `worktree/branch-protection-codeowners-2026.md` — protecting main from large files
- `lessons/llm-alignment-methods-2026.md` — model artifacts
- `deploy/` — large image handling in production

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage
- https://docs.github.com/en/repositories/working-with-files/managing-large-files/configuring-git-large-file-storage
- https://git-lfs.com/
- https://github.com/git-lfs/git-lfs
- https://discuss.huggingface.co/t/error-git-lfs-pull-downloads-files-much-larger-than-model-weights-and-does-not-stop/170286
- https://dvc.org/doc
- https://huggingface.co/docs/hub/models-downloading
- https://docs.github.com/en/repositories/working-with-files/managing-large-files
