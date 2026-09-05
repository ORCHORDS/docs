# CoAP Fleet Operations Playbook

## Purpose

Run day-2 operations for a CoAP-based constrained-device fleet: device onboarding, secure provisioning, firmware update, telemetry collection, and decommissioning. The playbook covers CoAP over UDP+DTLS, CoAP over TCP+TLS, and OSCORE (RFC 8613).

## Audience

IoT platform engineers, edge-collector team, fleet operators.

## Pre-conditions

1. CoAP server is reachable at the documented endpoint (CoAP port 5683 / DTLS port 5684).
2. The reference cards are current: `COAP_RFC_7252_VERSION_GOVERNANCE.md`, `MQTT_5_VERSION_GOVERNANCE.md`, `LWM2M_RFC_9195_VERSION_GOVERNANCE.md`.
3. Device identity (PSK or X.509 cert) is provisioned.
4. DTLS 1.3 or OSCORE is wired.
5. Observability stack is in place.

## Procedure

### 1. Device onboarding

1. Generate device identity:
   - PSK (256-bit) generated server-side, securely provisioned (per `SECRET_ROTATION_PLAYBOOK.md`).
   - X.509 cert issued by the device-management CA.
2. Provision device into the CoAP server's registry with the device endpoint URI: `coap://<host>:5683/<device-id>`.
3. Configure DTLS handshake: cipher suites per `COAP_RFC_7252_VERSION_GOVERNANCE.md` (AES-128-GCM, ChaCha20-Poly1305).
4. Validate first connection: the device must send `POST /.well-known/core` (RFC 6690) to advertise its resources.
5. Validate the discovery response is parseable.

### 2. Resource discovery

1. CoAP supports RFC 6690 (CoRE Link Format) for discovery.
2. Default endpoint: `/.well-known/core`.
3. The format is: `<uri>;rt="<resource-type>";if="<interface-type>";ct=<content-format>;sz=<size>;obs`.
4. Discoverable resource types include: `core.rd`, `core.ps`, `core.rp`, `ipso.<obj>`, etc.

### 3. Telemetry

1. The device publishes telemetry via:
   - `POST` to a server endpoint (CoAP over DTLS).
   - `Observe` (RFC 7641) for server-initiated notifications.
   - `Block-Wise` (RFC 7959) for large telemetry payloads.
2. Validate the server receives and stores telemetry.
3. Validate the device emits a heartbeat (e.g., every 60s) to detect offline devices.

### 4. Firmware update

1. Trigger firmware update via `POST /<device-id>/5/0/3` (LwM2M Firmware Update Object).
2. Device downloads the firmware from the URL provided in the package URI.
3. Validate firmware signature per COSE_Sign1 (see `CBOR_RFC_8949_VERSION_GOVERNANCE.md`).
4. Verify package integrity (SHA-256).
5. Atomic update: device enters `Downloaded → Updating → Idle` state machine.
6. On failure: roll back to prior firmware.
7. Validate update applied (post-update `GET /3/0/0` returns new firmware version).

### 5. Connectivity monitoring

1. Detect offline devices: missed heartbeats > 5 minutes.
2. Detect unstable connectivity: retransmit rate > 5/minute.
3. Detect OSCORE / DTLS failures: handshake failure rate > 0.1%.
4. Alert on: `coap.oscore.security.failures.count` > baseline.

### 6. Decommissioning

1. Initiate decommission: revoke the device cert or PSK at the issuer.
2. The device should fail handshake on next attempt (DTLS alert or OSCORE error).
3. Remove device entry from the registry.
4. Archive telemetry / state for retention period.
5. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` if decommissioning caused unexpected outages.

### 7. Observability

- `coap.connection.active` (gauge, broken by transport)
- `coap.connection.failed` (counter, by reason)
- `coap.message.rate` (counter, by method/code)
- `coap.observe.active` (gauge)
- `coap.retransmit.count` (counter)
- `coap.firmware.update.count` (counter, by result)
- `coap.oscore.security.failures.count` (counter)
- `coap.heartbeat.missed.count` (counter)

Audit log captures: `device_id`, `endpoint`, `method`, `code`, `mid` (message ID), `token`, `token_length`, `observe_seq`, `timestamp`, `source_ip`.

## Rollback

Rollback decisions:

- p99 request latency > 2x baseline → revert.
- Error rate > 5% for 5 minutes → revert.
- Firmware update failure rate > 1% → revert to last known-good firmware.

Rollback procedure:

1. Stop the deployment.
2. Revert the configuration to the last-known-good version.
3. Page the on-call fleet operator.
4. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `COAP_RFC_7252_VERSION_GOVERNANCE.md`
- `LWM2M_RFC_9195_VERSION_GOVERNANCE.md`
- `SECRET_ROTATION_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- RFC 6690 (CoRE Link Format): `https://www.rfc-editor.org/rfc/rfc6690`
- IETF CoRE WG: `https://datatracker.ietf.org/wg/core/about/`
