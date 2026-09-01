# TCP RFC 9293 Version Governance

## Purpose

Transmission Control Protocol (TCP) is a foundational transport protocol, but a generic claim of “TCP support” does not identify the governing specification, enabled extensions, operating-system behavior, or application assumptions.

Implementations and technical documentation should use RFC 9293 as the current base TCP specification and record companion RFCs separately when they affect interoperability, security, or operations.

## Current context and source status

**RFC 9293**, published in August 2022, is the Internet Standard for TCP and is identified as STD 7. It obsoletes RFCs 793, 879, 2873, 6093, 6429, 6528, and 6691, and updates TCP-related requirements in RFCs 1011, 1122, and 5961.

RFC 9293 consolidates the base protocol and accumulated corrections into one specification. It does not absorb every TCP extension or deployment practice. Congestion control, selective acknowledgments, explicit congestion notification, authentication options, and other capabilities remain governed by their applicable documents and implementation profiles.

## Governance pattern

1. Cite RFC 9293 for the base TCP protocol in architecture records, protocol inventories, and new requirements.
2. Inventory companion TCP extensions separately, including whether each is required, optional, disabled, or inherited from the operating system.
3. Record the implementation owner and boundary: kernel, user-space stack, proxy, load balancer, service mesh, appliance, or managed platform.
4. Map legacy RFC 793 references to their actual intent before replacing them. A citation update must not silently change an application contract or acceptance test.
5. Preserve externally visible behavior during stack upgrades unless a reviewed change explicitly authorizes different connection, reset, timeout, or option handling.
6. Test interoperability across supported peers and middleboxes rather than treating a library or kernel version as conformance evidence.
7. Retain evidence for the deployed implementation version, relevant configuration, test environment, observed packet behavior, and approved exceptions.
8. Review errata and later documents that update RFC 9293 before asserting a frozen profile.

## Migration from legacy references

A documentation migration should distinguish normative references from historical explanations. Replace RFC 793 as the base normative citation where RFC 9293 governs the requirement, but retain historical citations when they are needed to explain an old implementation, captured evidence, or another document’s wording.

For each migrated requirement:

- identify the behavior the old citation was intended to require;
- locate the corresponding current requirement or clarification;
- compare the deployed stack’s behavior with the intended contract;
- update tests and traceability records; and
- record unresolved deviations instead of declaring blanket conformance.

## Verification evidence

Useful evidence includes:

- packet captures from controlled interoperability tests;
- connection-state and reset-handling tests;
- boundary tests for sequence numbers, windows, retransmission, and reassembly;
- option-negotiation tests for the explicitly supported profile;
- tests across supported operating systems, proxies, load balancers, and network paths; and
- implementation documentation that identifies defaults and configuration changes.

Successful connection establishment alone is weak evidence. It does not establish correct behavior under loss, reordering, duplicate segments, simultaneous events, malformed traffic, or resource pressure.

## Failure modes

- Continuing to cite RFC 793 as though it were the current complete base specification.
- Claiming RFC 9293 conformance solely because an operating system exposes TCP sockets.
- Assuming RFC 9293 includes every TCP extension used by a platform.
- Updating references without checking whether legacy tests depended on obsolete or ambiguous behavior.
- Treating a packet capture from one successful connection as implementation-wide evidence.
- Omitting middleboxes and managed network services from the implementation inventory.
- Publishing internal addresses, packet payloads, credentials, or customer traffic as verification artifacts.

## Sources

- RFC 9293, Transmission Control Protocol (TCP): https://www.rfc-editor.org/rfc/rfc9293.html
- RFC Editor record for STD 7: https://www.rfc-editor.org/info/std7
- RFC Editor errata search: https://www.rfc-editor.org/errata-search/

Sources were checked on September 1, 2026.

## Scope note

This article governs the base-specification reference, implementation inventory, migration evidence, and compatibility review. It does not certify any TCP stack, define an application protocol’s timeout policy, or imply support for every TCP extension.
