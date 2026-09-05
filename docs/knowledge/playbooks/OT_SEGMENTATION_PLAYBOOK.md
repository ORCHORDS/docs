# OT/ICS Network Segmentation Playbook

## Purpose

Drive a predictable network segmentation between Operational Technology (OT) / Industrial Control Systems (ICS) and Information Technology (IT) / cloud workloads. Aligns with IEC 62443 zones-and-conduits model and Purdue Levels.

## Audience

OT engineers, IT engineers, security architect, control system owner.

## Pre-conditions

1. The reference cards are current: `IEC_62443_2024_IACS_GOVERNANCE.md`, `ISO_IEC_30141_2018_IOT_GOVERNANCE.md`.
2. The Purdue Level classification of the IACS is documented.
3. The asset owner has signed off on the segmentation design.
4. The target Security Level (SL-T) for each zone is declared.

## Procedure

### 1. Identify zones

1. Walk the IACS architecture and identify Zones per IEC 62443-3-3.
2. Each Zone is assigned a Purdue Level:

| Purdue Level | Description |
|---|---|
| Level 0 | Physical process (sensors, actuators) |
| Level 1 | Basic control (PLCs, RTUs) |
| Level 2 | Supervisory control (HMIs, SCADA) |
| Level 3 | Operations management (historians, batch control) |
| Level 3.5 | DMZ between OT and IT |
| Level 4 | Enterprise business systems (ERP, MES) |
| Level 5 | Enterprise network (corporate IT) |

3. Each Zone is assigned a target Security Level (SL-T) per IEC 62443.
4. Document Zone-to-Zone Conduits.

### 2. Identify conduits

1. Conduits are the logical communication paths between Zones.
2. Each Conduit is assigned:
   - A protocol (Modbus/TCP, DNP3, EtherNet/IP, IEC 60870-5-104, OPC UA, MQTT).
   - A target Security Level (SL-T).
   - An authentication mechanism.
   - An encryption requirement.

### 3. Implement segmentation

1. The Purdue Level 3.5 DMZ is the standard OT/IT boundary.
2. Use industrial firewalls, data diodes, or jump hosts at the DMZ.
3. Each Conduit must enforce:
   - Network segregation (VLAN, VRF, or physical).
   - Protocol filtering (e.g., only IEC 60870-5-104 allowed on a Conduit).
   - Authentication (e.g., mTLS, OPC UA certificates).
   - Encryption (where supported by the OT protocol).
4. Block all cross-zone traffic by default; allow only documented Conduits.

### 4. Authentication and authorization

| OT Protocol | Recommended authentication |
|---|---|
| Modbus/TCP | gateway + RADIUS / TACACS+ |
| DNP3 | DNP3-SA (Secure Authentication) per IEEE 1815-2012 |
| IEC 60870-5-104 | TLS 1.2+ per IEC 62351-3 |
| EtherNet/IP | CIP Security (IEC 62443-4-2) |
| OPC UA | OPC UA endpoint certificates per IEC 62443-4-2 |
| MQTT | TLS 1.3 client cert per IEC 62443-4-2 |

References: IEC 62351 (Power System Security), CIP Security (ODVA), OPC UA Security.

### 5. Monitoring

1. OT network monitoring with passive sensors (no active probes).
2. Monitoring tools:
   - Cisco Cyber Vision
   - Claroty
   - Dragos
   - Nozomi Networks
   - Microsoft Defender for IoT
3. Monitor every Conduit for:
   - Unauthorized protocols.
   - Failed authentication.
   - Configuration changes.
   - Network anomalies.

### 6. Maintenance windows

1. All segmentation changes happen during a planned maintenance window.
2. Maintenance window SLA: ≥ 24 hours advance notice to OT stakeholders.
3. Backup network configuration before the change.
4. Validate the change in a non-production OT lab before production.
5. Document the change ticket with: before/after configuration, security level impact, rollback plan.

### 7. Incident response

1. Detect: anomaly in Conduit traffic, failed authentication, unauthorized protocol.
2. Contain: increase SL-T for affected Zone; deny all traffic except documented Conduits.
3. Investigate: review OT audit logs, vendor advisories, threat intel feeds.
4. Remediate: apply patch, rotate creds, isolate compromised device.
5. Document: `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## Rollback

Rollback decisions:

- Production OT outage → revert segmentation immediately.
- SCADA operator reports degradation → investigate; revert if needed.
- Zone-to-zone communication broken → revert to last-known-good configuration.

Rollback procedure:

1. Revert the segmentation change to the last-known-good configuration.
2. Validate OT system operation.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` within 24 hours.

## Mandatory pre-flight (before adopting a new OT/ICS reference architecture)

1. Purdue Level classification is documented.
2. Zone and Conduit diagram is published.
3. Target SL-T is declared per Zone.
4. Authentication is configured per protocol.
5. Monitoring is wired.
6. Maintenance window policy is documented.

## References

- `IEC_62443_2024_IACS_GOVERNANCE.md`
- `ISO_IEC_30141_2018_IOT_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- IEC 62443-3-3:2013 Am1:2024: `https://www.iec.ch/store/`
- NIST SP 800-82 Rev. 3: `https://csrc.nist.gov/publications/detail/sp/800-82/rev-3/final`
- IEC 62351 (Power System Security): `https://www.iec.ch/store/`
- ISA/IEC 62443 series overview: `https://www.isa.org/standards-and-publications/isa-standards/isa-iec-62443-series-of-standards`
