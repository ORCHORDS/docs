# IMAP OBJECTID identity boundaries

**Issue:** IMAP OBJECTID exposes EMAILID and THREADID values intended to survive some mailbox changes. Treating them as globally unique, user-visible, or permanent across providers leaks identifiers and misthreads messages.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Scope identifiers by account/server, store capability and provenance, and fall back to UIDVALIDITY/UID plus Message-ID heuristics only through explicit reconciliation. Treat absent/changed THREADID as normal and never use either value for authorization.

## Verification

Test copy/move, expunge/reimport, server migration, threading changes, capability loss, duplicate Message-ID, multiple accounts, and reconnect after UIDVALIDITY change.

## Gotchas

EMAILID/THREADID are opaque server identifiers with defined scope, not RFC Message-ID replacements or cross-provider identity.

## Sources

- RFC Editor, [RFC 8474 IMAP OBJECTID](https://www.rfc-editor.org/rfc/rfc8474.html)
