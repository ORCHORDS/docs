# workers-vpc-least-privilege-design

**Issue:** A Worker needs private access to internal services, but a broad network binding exposes more destinations than the workload requires.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A Worker can reach a private service through a tunnel or VPC. The initial integration works, but the binding grants access to an entire private network, making destination review, egress control, and incident containment difficult.

## Root cause

Private connectivity is not automatically least privilege. Cloudflare Workers VPC supports narrowly declared services and broader network-level access; they have different operational and security consequences. A deployment that chooses the broadest binding by default turns application code into a network-discovery client.

**Source:** [Cloudflare Workers VPC](https://developers.cloudflare.com/workers-vpc/).

## Fix

Choose the narrowest connectivity model that satisfies the workload:

- use a service-level binding when the Worker needs a fixed host and port;
- use network-level access only when destinations are genuinely dynamic and the added discovery surface is justified;
- define destination ownership, allowed protocols, and authentication independently of VPC reachability;
- apply Gateway egress policy and logging where available; alert on denied or unexpected private destinations;
- keep tunnel, service, and Worker configuration in reviewed infrastructure code;
- document the beta/availability constraints and a rollback path before relying on the feature for a critical dependency.

## Verification

- **Allow:** the Worker reaches only the intended private service with valid application authentication.
- **Deny:** an undeclared host or port is blocked and produces a reviewable event.
- **Isolation:** another Worker without the binding cannot reach the target.
- **Rollback:** disabling the binding fails closed with a clear application error and no public fallback.

## Gotchas

- VPC reachability does not replace mTLS, service authentication, request authorization, or tenant isolation.
- A network binding is not a substitute for an egress allowlist.
- Do not expose a private service publicly to work around a missing binding.

## Related

- `cloudflare/zero-trust-access.md`
- `cloudflare/hyperdrive-best-practices.md`
- `patterns/multi-tenant-data-isolation.md`
