# W3C Web of Things Discovery Governance

## Purpose

The W3C Web of Things (WoT) Working Group produces specifications that enable interoperability across IoT platforms and devices. The WoT Discovery specification defines how things (devices, services, gateways) advertise themselves and how clients (consumers) can discover things that meet their needs. The specification uses WoT Thing Descriptions and a Discovery service interface to enable asynchronous, on-demand, and broadcast discovery. This article governs the application of WoT Discovery so an IoT deployment can interoperate with other WoT deployments through a consistent discovery mechanism.

## Scope

The specification applies to any IoT deployment using WoT Thing Descriptions. Within this knowledge base, the article covers the discovery mechanisms (direct, mediated, broadcast), the WoT Discovery service interface, the metadata used for discovery, and the documentation of the discovery configuration. It does not cover the WoT Thing Description itself (which is a separate specification); readers should consult that for the description format.

## Workflow

1. Identify the things the deployment exposes for discovery. Each thing should have a WoT Thing Description (TD).
3. Choose a discovery mechanism:
   - Direct: the client knows the thing's address and retrieves the TD directly (e.g., via HTTP GET to a known URL).
   - Mediated: a Discovery service maintains an index of TDs and provides search and retrieve operations.
   - Broadcast: the things announce themselves on a broadcast medium (e.g., DNS-SD, mDNS).
4. Implement the chosen discovery mechanism:
   - For direct: ensure TDs are reachable at known URLs.
   - For mediated: implement the WoT Discovery service interface — the operation set defined by the specification.
   - For broadcast: configure the broadcast announcements with the discovery information.
5. Define the metadata the things advertise: the security schemes, the protocol bindings, the endpoints, the semantic metadata (in JSON-LD), and any location or context.
6. Document the discovery configuration and the metadata schema.

## Controls and evidence

Discovery controls include the documented configuration, the TD validity, the discovery service implementation, and the broadcast configuration. Evidence includes the TD samples, the discovery service logs, and the broadcast configuration records.

## Validation

Validation should confirm the discovery mechanism operates as configured, the TDs are valid, the discovery service responds correctly, and the metadata is accurate. Sample-based testing across discovery scenarios confirms the configuration.

## Failure correction

Common failure modes: discovery metadata is incomplete (correct: ensure the TD has the required fields); broadcast configuration does not match the deployment's network topology (correct: configure broadcast for the target network); mediated discovery service is not reachable from clients (correct: ensure the service is reachable and accessible); TDs are out of date (correct: update TDs when the thing changes and align with the discovery mechanism).

## Limitations

WoT Discovery is one approach to IoT interoperability; deployments that use a different protocol may not interoperate without adaptation. The specification depends on the WoT Thing Description; things that do not produce TDs cannot be discovered through WoT Discovery. The broadcast mechanism is constrained by the underlying transport.

## Scope note

This article summarizes project-neutral platform use of W3C Web of Things Discovery. It does not assert any specific IoT deployment's conformance or claim any certification outcome.

## Canonical sources

- W3C Web of Things Discovery: https://www.w3.org/TR/wot-discovery/
- W3C Web of Things Thing Description 1.1: https://www.w3.org/TR/wot-thing-description11/