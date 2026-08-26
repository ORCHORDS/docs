# Hugging Face offline snapshot completeness

**Issue:** A warm Hub cache can make an offline model load appear reproducible even though the selected revision is mutable or the cached snapshot is incomplete.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Resolve a model or dataset revision to an immutable commit before promotion.
- Prefetch the complete approved snapshot, including tokenizer, configuration, custom-code, and weight shards required by the loader.
- Preserve a manifest of repository, commit, selected files, sizes, and digests with the release.
- Exercise the release with `HF_HUB_OFFLINE=1` and `local_files_only=True`; block outbound network access in the qualification job.
- Treat cache `refs` as mutable pointers and `snapshots` as materialized revisions; do not publish a cache directory as an artifact without verifying its closure.

## Verification

Start from an empty cache, download the pinned revision, disconnect the network, and load every supported path. Delete one required blob or shard and assert the load fails as incomplete rather than silently using another revision.

## Gotchas

Cache symlinks can be degraded to copies on filesystems without symlink support. File filters intentionally exclude content, so “complete” means complete for the declared loader contract, not necessarily every repository file.

## Official sources

- [Hugging Face Hub cache management](https://huggingface.co/docs/huggingface_hub/main/en/guides/manage-cache)
- [Hugging Face Hub snapshot download](https://huggingface.co/docs/huggingface_hub/main/package_reference/file_download)
