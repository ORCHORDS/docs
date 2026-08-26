# systemd-resolved route-only domains for split DNS

**Issue:** Sending every DNS query to a VPN or private resolver leaks unrelated names, while sending internal zones to public resolvers exposes private naming and causes intermittent failures.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Configure per-link DNS servers and route-only domains so each private suffix is routed to its authoritative link without becoming a search suffix. Use the `~domain` form for route-only domains and reserve `~.` for an intentional preferred route for all domains. Define behavior for overlapping suffixes, link priority, DNSSEC, and VPN teardown. Manage the configuration through the network manager that owns the link rather than competing runtime commands.

## Verification

Query representative private, public, nonexistent, IPv4, and IPv6 names while the private link is up and down. Inspect `resolvectl status` and query routing, capture test traffic to prove each suffix reaches only the intended resolver, and confirm cache flushing or TTL behavior during transitions.

## Gotchas

Route-only domains affect resolver routing but do not add a search suffix. Applications that bypass the system resolver ignore this policy. A catch-all `~.` can unexpectedly supersede other links depending on route metrics and configuration.

## Official sources

- https://www.freedesktop.org/software/systemd/man/latest/systemd-resolved.html
- https://www.freedesktop.org/software/systemd/man/latest/resolved.conf.html
- https://www.freedesktop.org/software/systemd/man/latest/resolvectl.html
