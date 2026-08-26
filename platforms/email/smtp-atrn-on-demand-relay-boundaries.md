# SMTP ATRN on-demand relay boundaries

**Issue:** An intermittently connected domain needs queued mail but exposes an unauthenticated TURN-style command or assumes ATRN is ordinary mailbox retrieval.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; deployment support is limited

RFC 2645 ATRN permits an authenticated client to request reversal of the SMTP connection so queued mail can be delivered. Treat requested domains as authorization scope and keep modern retrieval alternatives available.

**Source:** [RFC 2645: On-Demand Mail Relay](https://www.rfc-editor.org/rfc/rfc2645)

## Controls

- use only after EHLO advertisement and successful strong authentication;
- authorize every requested domain against the authenticated identity;
- require protected transport and rate-limit reversals;
- isolate relay queues and prevent open-relay behavior;
- log bounded operational metadata without message contents or credentials.

## Verification

Test unauthenticated use, unauthorized/multiple domains, empty queue, reconnect, partial delivery, duplicate request, STARTTLS re-EHLO, timeout, and concurrent sessions. Confirm failure cannot relay third-party mail.

## Gotchas

ATRN is not POP/IMAP and does not provide mailbox semantics. Limited ecosystem support may make store-and-forward through a managed provider safer. Connection reversal complicates firewalls and observability.
