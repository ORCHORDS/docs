# SMTP ETRN remote queue-start controls

**Issue:** A domain with intermittent connectivity uses unauthenticated remote queue triggers that can amplify work or disclose queued-domain behavior.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** standards-defined; deployment support is limited

RFC 1985 ETRN lets a client request that a server start queued delivery for a domain/queue name. Treat it as a bounded trigger, not authentication, mailbox retrieval, or guaranteed immediate delivery.

**Source:** [RFC 1985: SMTP Service Extension for Remote Message Queue Starting](https://www.rfc-editor.org/rfc/rfc1985)

## Controls

- use only after EHLO advertisement;
- authorize/rate-limit triggerable queue names by network and policy;
- normalize exact domain syntax without wildcard expansion;
- coalesce repeated triggers and bound worker creation;
- avoid revealing queue depth or recipient data;
- retain normal retry scheduling if unsupported.

## Verification

Test unknown/unauthorized domains, empty queue, repeated/concurrent ETRN, delivery failure, disconnect, STARTTLS re-EHLO, and abuse bursts. Confirm ETRN cannot turn the host into an open relay.

## Gotchas

ETRN starts an attempt; it does not reverse the connection like ATRN or guarantee completion. Widespread modern support is limited. A successful reply is not recipient delivery.
