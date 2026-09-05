# MQTT v5 Fleet Provisioning and Decommissioning Playbook

## Purpose

Stand up, onboard, monitor, and decommission an MQTT v5 fleet (devices or services that speak MQTT) in the `orchords-docs` reference architecture. Covers topic structure, authentication, authorization, shared subscriptions, and observability.

## Audience

IoT platform engineers, edge-collector team, fleet-management operators.

## Pre-conditions

1. MQTT broker version supports MQTT v5.0 (and Errata 01 if cited in the reference card).
2. Broker is configured for TLS 1.3, OAuth 2.0 bearer token authentication (or X.509 client cert).
3. Topic structure is published in `docs/knowledge/reference/MQTT_TOPIC_NAMING.md` (or equivalent).
4. Authorization is enforced at topic level (`$share/...` topics must be authorized identically to the underlying topic).
5. The reference cards for MQTT are current: `MQTT_5_VERSION_GOVERNANCE.md`.

## Procedure

### 1. Topic structure design

1. Define the topic hierarchy in advance. Pattern: `<namespace>/<environment>/<tenant>/<device-class>/<device-id>/<event-class>`.
2. Topic wildcards:
   - Single level: `+`
   - Multi level: `#`
3. Topic aliases: enable `Topic Alias Maximum` for high-frequency publishers to reduce payload size.
4. Shared subscriptions: `$share/<consumer-group>/<topic-filter>` for horizontal scaling.

### 2. Authentication

| Authentication method | Use case | Configuration |
|---|---|---|
| X.509 client cert | high-assurance device fleets | broker enforces mutual TLS, client supplies device cert signed by the project's CA |
| OAuth 2.0 bearer token | human-facing or machine-to-machine | MQTT v5 `Authentication Method` + `Authentication Data` challenge/response |
| Username/password | legacy or low-assurance | NOT recommended for production; migrate to OAuth 2.0 |

### 3. Authorization

Authorization is enforced at topic level. The project's authorization matrix is the rule `topic-pattern -> publish|subscribe`:

| Topic pattern | publish | subscribe |
|---|---|---|
| `orchords/<env>/<tenant>/<class>/<device-id>/telemetry/+` | device | service |
| `orchords/<env>/<tenant>/<class>/<device-id>/command/+` | service | device |
| `orchords/<env>/<tenant>/<class>/<device-id>/ack/+` | device | service |
| `orchords/<env>/+/+/+/+/+/+` | n/a | telemetry consumer (shared) |

Rules must be policy-file-driven (not hard-coded) and reviewable.

### 4. Onboarding

1. Issue device identity (X.509 cert or bearer-token registration).
2. Provision topic ACL in the broker.
3. Validate the device connects with `Session Expiry Interval = 0` (clean session for first connection).
4. Validate the device publishes a heartbeat topic within 5 minutes.
5. Validate the device receives the `command/<device-id>/...` topic.

### 5. Shared subscriptions

1. For each horizontal-scaling consumer group, use `$share/<group>/<topic-filter>`.
2. The broker load-balances messages across the subscribed clients.
3. Each shared subscription must have ≥ 2 active clients in steady state; alarms on single-client shared subscriptions.

### 6. Observability

- `mqtt.connection.count` (gauge)
- `mqtt.connection.failed.count` (counter)
- `mqtt.publish.bytes` / `mqtt.deliver.bytes` (counter)
- `mqtt.in_flight.count` (gauge)
- `mqtt.shared_subscription.lag_ms` (gauge per group)
- `mqtt.session.expired.count` (counter)
- `mqtt.retained.count` (gauge)

The audit log captures `client_id`, `topic`, `qos`, `retain`, `payload_size`, and `result`.

### 7. Decommissioning

1. Issue a `DISCONNECT` with reason `0x04` (Disconnect with Will Message) to the device.
2. Wait for graceful disconnect (≤ 30 seconds).
3. Revoke the device cert or bearer token at the issuer.
4. Remove topic ACLs.
5. Confirm the device no longer appears in `mqtt.connection.count` for ≥ 5 minutes.
6. Retain audit log entries for the device for the project's standard retention period.

## Rollback

If the broker change causes widespread disconnects, the playbook rolls back to the previous broker config:

1. Revert broker configuration to the last-known-good version.
2. Restart broker.
3. Validate device reconnect rate.
4. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` for the broker-config change.

## References

- `MQTT_5_VERSION_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- OASIS MQTT v5.0: `https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html`
- HiveMQ shared subscriptions: `https://www.hivemq.com/blog/mqtt5-essentials-part-10-shared-subscriptions/`
