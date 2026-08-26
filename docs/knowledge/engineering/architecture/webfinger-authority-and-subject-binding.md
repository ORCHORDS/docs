# WebFinger authority and subject binding

**Issue:** RFC 7033 discovers information about a URI-identified subject through an HTTPS well-known endpoint. The queried host, returned subject, aliases, and link targets are different trust decisions.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Normalize and validate the resource URI; derive the discovery authority by the RFC procedure; require HTTPS; bind the response subject to the request; allowlist relation handling and validate each target independently.

## Verification

Test acct and HTTPS resources, Unicode/IDNA, redirects, mismatched subjects, duplicate links, unknown relations, cache expiry, and attacker-controlled aliases.

## Gotchas

Discovery metadata is not proof that the subject controls an alias or linked service. Do not send credentials to link targets inherited from discovery.

## Official sources

- https://www.rfc-editor.org/rfc/rfc7033
