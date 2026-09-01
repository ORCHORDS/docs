# IETF SNMPv3 USM Key Rotation (RFC 3414)

## Purpose

SNMP is the network-management protocol of record for routers, switches, and many service elements. Versions prior to SNMPv3 expose management data in cleartext and allow trivial impersonation of managers. RFC 3414 defines the User-based Security Model (USM) for SNMPv3, which adds authentication and privacy and, critically, supplies the key-change mechanism that operators rely on for credential rotation. This article summarizes USM as an operations reference; it does not replace the RFC or claim implementation guidance.

## What USM provides

USM is one of two security models permitted for SNMPv3 messages (the other is the Transport Security Model). The USM services are:

- **Data integrity** — proving that the message body has not been modified in transit.
- **Data origin authentication** — binding the message to a specific user identity.
- **Data confidentiality** — encrypting the message body against eavesdroppers.
- **Message timeliness** — proving the message is recent, with a 150-second time window enforced via the authoritative engine's boots and time values.

USM explicitly does not address end-to-end security or access control beyond message protection. Access control is the role of the View-based Access Control Model (VACM, RFC 3415). USM does not address denial-of-service protection either; that must be handled by the network design and the deployment.

## Authentication protocols

RFC 3414 requires HMAC-MD5-96 for authentication and recommends HMAC-SHA-96. Later iterations of the security community have introduced newer HMAC modes; the standard remains valid for HMAC-MD5-96 and HMAC-SHA-96 implementations. The choice of authentication protocol should be made to align with the organization's cryptographic policy and the equipment's supported algorithms.

## Privacy

USM specifies CBC-DES for privacy as the default. CBC-DES is deprecated cryptography, and operational deployments should prefer AES (RFC 3826) or the modern AES-192/AES-256 modes in current use. CBC-DES remains the minimum required to conform to RFC 3414, but operators should validate the privacy mode in use on every device, not only the configured mode.

## Key localization

USM uses key localization: a master key shared between manager and agent is combined with the authoritative engine's `snmpEngineID` value to derive the key used for each specific agent. The implication for operations is that the master key shared with the manager is not the key stored on the device. Compromise of the device key does not immediately compromise the manager; compromise of the master key plus the `snmpEngineID` does compromise every device.

## Key rotation

USM supports key change operations per user and per protocol (authentication and privacy). The rotation procedure is:

1. Confirm the manager and agent agree on protocol versions, usernames, and the authoritative `snmpEngineID`.
2. Change the authentication key on the agent first or on the manager first, depending on protocol ordering.
3. Use the new authentication key for the next poll cycle and validate monitoring is unaffected.
4. Change the privacy key.
5. Continue parallel use until both sides confirm the new keys.
6. Update the centralized monitoring record that lists the protocol and key generation used per agent.

Rotation is safer when staged: rotating one key at a time, with empirical confirmation between steps, prevents the routine failure of reverting a key that no longer matches. Where equipment does not allow gradual rotation, perform the rotation during a documented maintenance window with a defined rollback path. The rollback path is rarely used, but defining it makes the cutover shorter because the operator has already decided what to do.

## Operational workflow

1. Inventory SNMP-managed devices; record the SNMP version, security model, security level, authentication protocol, and privacy protocol in use.
2. For each device that still runs SNMPv1, SNMPv2c, or community-based polling, plan a transition to SNMPv3 with USM (or higher-grade cryptography where supported).
3. Define users per device or per device class; ensure usernames are unique within the management domain.
4. Apply key localization by deriving or configuring per-engine keys; never reuse a master key across unrelated devices.
5. Schedule key rotations; align rotation with the operator's broader cryptographic policy.
6. Confirm rotation by polling and trap functionality.
7. Maintain a centralized inventory of credentials, rotation history, and supported protocol versions per device.

## Validation evidence

Retain the SNMP version matrix per device, the authentication and privacy protocols in use, the user catalog, the key rotation schedule and history, the user notification banner and configuration record, the result of polls and traps during each rotation, the protocol violation alerts, and a periodic review of devices still using older security models. Maintain evidence that the unique master key per device or device class is observed in configuration management.

## Failure modes

Failure modes include community strings being treated as security-grade credentials, devices being left on default well-known strings, master keys being shared between unrelated devices, rotation being performed for both authentication and privacy simultaneously without rollback steps, and security models not being upgraded despite published vulnerabilities. The MITM threat model that USM addresses can still be valid long after USM is technically deployed; rotate keys regularly even when the cryptography itself remains strong.

## Canonical sources

- RFC 3414, User-based Security Model (USM) for version 3 of the Simple Network Management Protocol (SNMPv3): https://www.rfc-editor.org/rfc/rfc3414
- RFC 3415, View-based Access Control Model (VACM) for the Simple Network Management Protocol (SNMP): https://www.rfc-editor.org/rfc/rfc3415
- RFC 3826, Advanced Encryption Standard (AES) Cipher Algorithm in the SNMP User-based Security Model: https://www.rfc-editor.org/rfc/rfc3826

## Scope note

This article summarizes USM as an operations reference; specific vendor configuration, including per-vendor key-change commands and reachability planning, remains a separate design and runbook task.
