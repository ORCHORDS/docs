# Git wire-protocol version policy

**Problem**

Forcing a Git protocol version changes negotiation features and compatibility across clients, servers, proxies, and transports.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for compatibility diagnosis or measured performance policy, not as an arbitrary global tweak.

## Controls

- Pin supported client/server versions.
- Canary protocol v2 and retain fallback.
- Keep authentication and ref authorization unchanged.

## Implementation

- Set `protocol.version` in controlled scope.
- Record transport and server capability advertisement.
- Avoid user-global changes on shared runners.

## Tests

- Clone/fetch/push over HTTPS, SSH, and local transports; test proxy, old server, partial clone, and many refs.

## Gotchas

- Unsupported versions may fall back or fail by transport.
- Protocol version is not TLS version.
- Performance varies by ref shape.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-protocolversion)
