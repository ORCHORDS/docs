# Constrain SSH Certificates with Principals and Critical Options

**Issue:** A valid SSH user certificate can grant broader access than intended when principals, validity, source restrictions, or session capabilities are left implicit.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Issue short-lived certificates with an auditable key ID and the smallest explicit principal set.
- Configure servers to trust dedicated user and host CAs separately.
- Map principals through reviewed server policy; do not treat the certificate key ID as authorization.
- Clear default certificate permissions before selectively enabling required extensions.
- Use critical options such as source-address or force-command where appropriate; reject unknown critical options.
- Protect the CA key, separate issuance roles, and publish a rapid trust-removal and emergency replacement runbook.
- Log serial, key ID, principals, CA fingerprint, validity window, and target at authentication.

## Verification

- Attempt login with the wrong principal, outside validity, from a disallowed source, and to a host trusting only the other CA class.
- Assert prohibited forwarding, PTY, agent, and user-rc capabilities remain unavailable.
- Test unknown critical options fail closed.
- Revoke CA trust in a rehearsal and measure propagation across the fleet.

## Gotchas

Principals are authorization names, not necessarily operating-system usernames. Extensions are permissive features while critical options impose mandatory restrictions; confusing the two can invert policy.

## Official sources

- [OpenBSD ssh-keygen manual](https://man.openbsd.org/ssh-keygen)
- [OpenBSD sshd manual](https://man.openbsd.org/sshd)
