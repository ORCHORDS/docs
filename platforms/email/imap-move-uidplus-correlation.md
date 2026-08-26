# IMAP MOVE and UIDPLUS correlation

**Issue:** A client implements “move” as copy, mark deleted, and expunge without preserving UID correlation or isolating unrelated expunges. Retries can create duplicates, delete the wrong messages, or lose the mapping to the destination mailbox.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Prefer `UID MOVE` only when the server advertises MOVE. Track messages by UID plus mailbox `UIDVALIDITY`, never by volatile sequence number. When UIDPLUS is present, consume `COPYUID` to correlate source and destination UID sets and validate that the mapping cardinality is consistent.

Treat MOVE as a single requested action but not as a distributed transaction with local storage. Persist an operation identifier and reconcile both mailboxes after an ambiguous disconnect. If MOVE is unavailable, use `UID COPY`, verify success and any `COPYUID`, mark only the intended UIDs deleted, then use `UID EXPUNGE` when supported. A broad EXPUNGE can remove other clients' deleted messages and needs an explicit policy.

## Verification

Test partial sets, nonexistent destination, quota failure, concurrent expunges, duplicate retry after response loss, UIDPLUS absent, mapping gaps, destination `UIDVALIDITY` change, ACL denial, and self-move. Verify unrelated messages are never expunged and each source UID has at most one accepted destination mapping.

## Gotchas

Destination UIDs differ from source UIDs. Untagged EXPUNGE responses may be unrelated to the MOVE, and a tagged failure does not by itself prove that no server-side effect occurred.

## Sources

- RFC Editor, [RFC 6851: IMAP MOVE Extension](https://www.rfc-editor.org/rfc/rfc6851.html)
- RFC Editor, [RFC 4315: IMAP UIDPLUS Extension](https://www.rfc-editor.org/rfc/rfc4315.html)
