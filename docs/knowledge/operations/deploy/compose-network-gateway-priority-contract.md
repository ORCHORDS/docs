# Docker Compose network gateway-priority contract

**Issue**

A service attached to multiple networks needs an explicit default-gateway selection; attachment order is not a durable routing policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `gw_priority` deliberately and keep only one highest-priority network.
- Separate gateway choice from `priority`, interface naming, and MAC assignment.
- Document egress policy and DNS expectations per network.

## Verification

1. Inspect routes and source addresses inside the container.
2. Reorder YAML networks and require unchanged routing.
3. Test recreate, engine upgrade, IPv4/IPv6, and unavailable networks.

## Gotchas

- Network priority does not set gateway priority.
- Equal priorities can be ambiguous.
- Host firewall policy still governs traffic.

## Official source

- [Official documentation](https://docs.docker.com/reference/compose-file/services/#gw_priority)
