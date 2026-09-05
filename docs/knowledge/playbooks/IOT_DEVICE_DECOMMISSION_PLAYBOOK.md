# IoT Device Decommissioning Playbook

## Purpose

Safely retire a single IoT device or a fleet of devices from production, ensuring that all sensitive data is erased, identity is revoked, telemetry is archived, and the device is removed from observability stacks without leaving a gap in monitoring.

## Audience

IoT platform engineers, security engineer, asset owner.

## Pre-conditions

1. The device has a known owner (asset owner / customer).
2. The device has a registered identity (PSK, X.509, RPK).
3. The device is currently reachable OR has a documented last-known location.
4. The reference cards are current: `MQTT_FLEET_PROVISIONING_PLAYBOOK.md`, `COAP_FLEET_OPERATIONS_PLAYBOOK.md`, `SECRET_ROTATION_PLAYBOOK.md`.
5. The asset owner has signed off on the decommission.

## Procedure

### 1. Plan decommissioning

1. Open a decommission ticket with:
   - Device ID(s) or device serial numbers.
   - Decommission reason (end-of-life, transfer, faulty, security incident).
   - Decommission date.
   - Owner sign-off.
2. Notify the asset owner.
3. Schedule a maintenance window if the device is in production.
4. Notify downstream consumers (data pipelines, billing systems, asset registry).

### 2. Archive data

1. Archive telemetry for the retention period (default 13 months).
2. Archive state snapshots (last-known configuration).
3. Archive audit log entries for the device.
4. Confirm archives are written to immutable storage.

### 3. Quarantine (if security-driven decommissioning)

1. Revoke the device's identity at the issuer:
   - X.509 cert: add to CRL.
   - PSK: rotate or revoke.
   - RPK: revoke at the trust store.
2. Block network access to the device management plane (ACL deny-all).
3. Confirm the device cannot reach the management endpoint.

### 4. Erase device data

1. Send a `reset` command to the device (MQTT, CoAP, LwM2M, or vendor-specific).
2. Verify the device confirms the reset.
3. If the device is unreachable: mark it `stale` and document the unreachable state.
4. Validate that subsequent reads return no user data.

### 5. Remove from registries

1. Remove the device from the fleet registry (MQTT broker, CoAP server, LwM2M server).
2. Remove the device from the asset management system.
3. Remove the device from the observability stack (Prometheus targets, log aggregators).
4. Remove the device from the billing system (if applicable).
5. Remove the device from the customer-facing dashboard.

### 6. Physical decommission (if required)

1. Document the physical decommission (return-to-vendor, recycling, destruction).
2. Confirm the device is destroyed if the data class is restricted.
3. Update the asset lifecycle record.

### 7. Audit and confirm

1. Confirm the device is unreachable on the network.
2. Confirm the device identity is revoked.
3. Confirm the device data is erased.
4. Confirm the device is removed from all registries.
5. Document the decommissioning completion in the audit log.
6. Close the decommission ticket.

### 8. Post-decommission monitoring

1. Monitor for any traffic from the decommissioned device's IP/MAC (where possible).
2. If traffic is detected: investigate as a security incident.
3. If no traffic for ≥ 30 days: finalize the decommission.

## Rollback

Rollback of a decommission is possible only if the device is still reachable and the identity has not yet been revoked at the source. After the source-identity revocation, rollback is not possible without re-issuing identity.

## Mandatory pre-flight (before decommissioning a fleet of devices)

1. Bulk-revoke all device identities.
2. Bulk-send reset commands.
3. Bulk-archive telemetry.
4. Bulk-remove from registries.
5. Validate the bulk decommission completed for every device in the fleet.

## References

- `MQTT_FLEET_PROVISIONING_PLAYBOOK.md`
- `COAP_FLEET_OPERATIONS_PLAYBOOK.md`
- `SECRET_ROTATION_PLAYBOOK.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- ETSI EN 303 645 (Provision 11 — delete user data): `https://www.etsi.org/deliver/etsi_en/303600_303699/303645/`
- NIST SP 800-88 Rev. 1 (Media Sanitization): `https://csrc.nist.gov/publications/detail/sp/800-88/rev-1/final`
