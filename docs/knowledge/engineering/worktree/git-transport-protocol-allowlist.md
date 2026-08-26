# Git transport-protocol allowlist

**Issue:** Recursive submodules, URL rewrites, and remote helpers can cause an unattended Git command to invoke a transport the caller never intended to authorize.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Set `protocol.allow` and per-transport `protocol.<name>.allow` in protected system or runner configuration. Prefer a deny-by-default automation profile with only required transports marked `always`; keep `ext` and unneeded remote helpers disabled, and allow local `file` transport only for a narrowly reviewed workflow. Treat `user` as an interactive-origin distinction, not a substitute for sandboxing or repository authorization.

Evaluate policy after `url.<base>.insteadOf` rewriting because the rewritten URL's transport is what Git checks. Inventory every main remote and nested submodule URL before tightening the allowlist, keep configuration outside repository-controlled scope, and pair transport permission with host, credential, path, and ref authorization.

## Verification

Test HTTPS, SSH, local paths, `file://`, `ext`, a custom remote helper, rewritten URLs, and recursive submodule initialization in interactive and non-interactive contexts. Require denied protocols to fail before helper execution and confirm approved clones/fetches/pushes still use the intended credential boundary.

## Gotchas

- `protocol.version` controls wire negotiation, not which transports are permitted.
- A permitted transport can still reach an untrusted host or path.
- Repository-local config must not be able to relax a protected runner policy.

## Official source

- [Git protocol.allow configuration](https://git-scm.com/docs/git-config#Documentation/git-config.txt-protocolallow)
