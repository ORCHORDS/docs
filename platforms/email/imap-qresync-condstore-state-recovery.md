# IMAP QRESYNC and CONDSTORE state recovery

**Issue:** An offline IMAP client reconnects and treats its cached UID list and flags as current. Concurrent flag edits, expunges, or a changed `UIDVALIDITY` can then resurrect deleted mail, lose updates, or attach state to the wrong message.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Negotiate capabilities; never send QRESYNC syntax unless the server advertises it. Persist mailbox identity as server/account, mailbox, `UIDVALIDITY`, highest known UID, and highest modification sequence. Enable QRESYNC after authentication, then supply only state from the same mailbox generation.

Apply `VANISHED` and changed `FETCH` data as one ordered reconciliation transaction. If `UIDVALIDITY` changes, `NOMODSEQ` is returned, state is incomplete, or the server loses the capability, discard the incremental cursor and perform a bounded full resynchronization. Use CONDSTORE's `UNCHANGEDSINCE` for conditional flag writes and surface the `MODIFIED` set as conflicts rather than silently overwriting remote changes.

## Verification

Test concurrent clients, offline flag edits, expunge while disconnected, `VANISHED (EARLIER)`, empty mailboxes, UID gaps, mod-sequence rollover boundaries, capability loss, server migration, changed `UIDVALIDITY`, interrupted reconciliation, and replay after a local transaction failure. Assert that applying the same server responses twice is harmless.

## Gotchas

Modification sequences are opaque and scoped to a mailbox generation; they are not timestamps. QRESYNC reduces transfer volume but does not remove the need for a full-resync fallback or conflict policy.

## Sources

- RFC Editor, [RFC 7162: IMAP Extensions for CONDSTORE and QRESYNC](https://www.rfc-editor.org/rfc/rfc7162.html)
- RFC Editor, [RFC 9051: IMAP4rev2](https://www.rfc-editor.org/rfc/rfc9051.html)
