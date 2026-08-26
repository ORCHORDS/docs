# Sequentialize GitHub Contents API Mutations

**Issue:** Parallel create, update, and delete requests against a changing branch can conflict or apply against stale blob state.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

- Serialize Contents API mutations that update or delete files on the same branch, especially create/update paired with delete.
- Fetch the current file immediately before replacement or deletion and pass its current blob SHA.
- Treat HTTP 409 as a state conflict requiring refetch and reconciliation, not blind retry.
- Use distinct-path parallelism only when the workflow can tolerate independent commits and branch-head movement.
- Fetch every written path back from the target branch before counting the mutation as complete.

## Verification

- Run two controlled same-path mutations and verify the loser refetches rather than overwriting.
- Change a blob between read and delete and confirm stale-SHA deletion fails.
- Compare resulting commit parentage and target-branch content after a batch.

## Gotchas

- Validate feature and specification maturity against the cited official source.
- Avoid secrets, personal data, and restricted operational details in examples or evidence.
- Reassess after scope, dependency, protocol, or policy changes.

## Sources

- https://docs.github.com/en/rest/repos/contents
