# Git bundle-URI clone bootstrap controls

**Issue**

Bundle URIs can accelerate large clones by preloading objects from infrastructure separate from the authoritative origin, creating freshness, integrity, availability, and data-exposure decisions that ordinary origin-only clone policy does not cover.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Allowlist HTTPS bundle origins and bind each advertised list to the expected repository identity.
- Treat the origin fetch as authoritative; a bundle failure must degrade to a normal clone, not produce an unverified checkout.
- Publish immutable content-addressed bundles or signed manifests and constrain access equivalently to the origin.
- Match full and partial-clone filters explicitly; record bundle list version, creation token, final HEAD, and origin URL.
- Expire unreachable objects according to the repository retention policy and protect bundles from cross-tenant cache keys.

## Verification

1. Clone with and without `--bundle-uri` and require identical requested refs and commit IDs.
2. Test stale, truncated, unavailable, unauthorized, and wrong-repository bundles.
3. Run `git fsck --strict`, then fetch from the origin and build from a clean worktree.
4. Measure bytes, clone time, fallback time, and duplicate downloads.

## Gotchas

- `--bundle-uri` is incompatible with shallow clone options.
- Bundle tips live under hidden `refs/bundle/*`.
- Bundles may contain more reachable history than a single-branch consumer requested.
- Creation tokens are download heuristics, not proof of trust or freshness.

## Official source

- [Official documentation](https://git-scm.com/docs/bundle-uri)
