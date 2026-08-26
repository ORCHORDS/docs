# Git cat-file batch-command buffering contract

**Issue:** Starting one Git process per object wastes time, while a long-lived buffered `cat-file` process can deadlock or misframe output when the caller forgets to flush or parse lengths exactly.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use one pinned `git cat-file --batch-command` process for high-volume object `info` and `contents` requests.
- Enable `--buffer` only with an explicit flush policy. Send `flush` before waiting for output and bound both the pending request count and bytes.
- Parse the documented protocol by declared object type and size; never use line splitting for arbitrary blob contents. Treat missing and ambiguous object responses as typed failures.
- Validate requested object expressions and repository selection. `--batch-all-objects` also visits unreachable objects and alternate object stores, which can expose data outside a reachability-based inventory.
- Use `--unordered` only when output order is not part of the consumer contract, and pin mailmap or replacement-object behavior explicitly.

## Verification

Mix `info`, `contents`, and `flush`; include empty, binary, large, missing, and replaced objects; kill either side mid-frame; exceed the buffer budget; and read alternate and unreachable objects in a disposable repository. Assert request/response correlation and memory bounds.

## Gotchas

- With buffering enabled, no output is promised until a flush.
- Object content may contain any byte sequence; its declared length is the framing boundary.
- A faster all-object scan can broaden the data exposure being scanned.

## Official source

- [Git cat-file batch-command and buffering](https://git-scm.com/docs/git-cat-file)
