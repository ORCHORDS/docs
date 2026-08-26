# IMAP special-use mailbox discovery

**Issue:** Clients infer Sent, Drafts, Trash, Junk, Archive, or All Mail from localized mailbox names. The guess breaks when a server uses another language, exposes virtual mailboxes, or lets users rename folders.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Protocol boundary

RFC 6154 adds the `SPECIAL-USE` capability and special-use attributes to IMAP `LIST` responses. Treat those attributes as server-supplied mailbox roles, not as presentation labels:

- `\Sent`, `\Drafts`, `\Trash`, `\Junk`, and `\Archive` identify filing destinations.
- `\Flagged` identifies messages selected by the Flagged flag.
- `\All` can be a virtual aggregate. Never assume that moving or deleting through it has ordinary physical-folder semantics.
- `\NoSelect` still means the returned name cannot be selected, even if another attribute is present.

A mailbox name and a mailbox role are separate fields. Preserve the exact server mailbox identifier for commands and local cache keys; localize only the UI label.

## Implementation controls

1. After authentication, record whether the server advertised `SPECIAL-USE`. Issue a `LIST` request that asks for special-use attributes and parse response attributes case-insensitively.
2. Build a per-account role map from the response. Do not merge maps across accounts or providers.
3. Tolerate no match and multiple matches. If a write action needs one destination, require a deterministic account setting or user choice; never silently choose by English name.
4. Treat an unrecognized backslash attribute as an extension. Preserve it if the data model permits and ignore it for behavior until supported.
5. Refresh discovery after mailbox create, rename, delete, subscription changes, or an account reconnect. A cached role is not permanent.
6. If the server advertises `CREATE-SPECIAL-USE`, creation can request a role. A failed or unsupported request must not fall back to creating an ambiguously named mailbox without confirmation.
7. Keep folder-role discovery independent from message-thread identifiers and from provider-specific APIs.

## Verification

Test fixtures should cover a localized tree, nested names, an aggregate `\All` mailbox, a `\NoSelect` parent, duplicate role claims, no special-use attributes, unknown extension attributes, and a role changing after rename. Assert that send/archive/delete actions use the selected mailbox identifier, not the displayed label.

Capture the capability response and raw `LIST` attributes in redacted diagnostics. Alert on role ambiguity only when it blocks an action; ambiguity itself is valid protocol input.

## Gotchas

- `SPECIAL-USE` describes purpose; it does not grant permission or guarantee selectability.
- A missing attribute does not prove the mailbox has no conventional purpose.
- Display-name heuristics can be an explicit, user-visible compatibility mode, but must never overwrite discovered roles.
- Server hierarchy delimiters and modified UTF-7/UTF-8 handling remain separate IMAP concerns.

## Sources

- [RFC 6154 — IMAP LIST Extension for Special-Use Mailboxes](https://www.rfc-editor.org/rfc/rfc6154.html)
