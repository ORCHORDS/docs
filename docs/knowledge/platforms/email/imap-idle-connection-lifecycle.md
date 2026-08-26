# IMAP IDLE connection lifecycle

**Issue:** A mail client treats IMAP IDLE as a permanent push subscription. NATs, server inactivity limits, mobile network changes, and an incorrect `DONE` transition leave the client silently stale or corrupt the command stream.

**Date:** 2026-08-18
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Controls and implementation

Use IDLE only after the server advertises the capability. Enter it from a valid authenticated or selected state, wait for the continuation response, and keep reading unsolicited responses. To issue another command, send `DONE`, wait for the tagged completion of the IDLE command, and only then send the next command.

Own the connection with a single state machine so a poller and an IDLE loop cannot write concurrently. Refresh the IDLE session before the server's inactivity window, add jitter across accounts, and use bounded exponential backoff after disconnects. On reconnect, resume through UID/mod-sequence synchronization; IDLE notifications are hints to synchronize, not a durable event log.

## Verification

Test no IDLE capability, delayed continuation, responses arriving around `DONE`, half-open TCP, server logout, 29-minute refresh, sleep/wake, Wi-Fi-to-cellular changes, authentication expiry, mailbox switch, and shutdown during each state. Confirm commands are never interleaved while the server expects continuation data.

## Gotchas

The RFC advises reissuing IDLE at least every 29 minutes, but intermediaries can time out sooner. An `EXISTS` response does not contain the message body, and missed notifications must be recovered from mailbox state.

## Sources

- RFC Editor, [RFC 2177: IMAP4 IDLE command](https://www.rfc-editor.org/rfc/rfc2177.html)
- RFC Editor, [RFC 9051: IMAP4rev2](https://www.rfc-editor.org/rfc/rfc9051.html)
