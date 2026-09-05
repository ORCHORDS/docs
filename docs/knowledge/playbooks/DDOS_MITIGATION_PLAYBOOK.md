# DDoS Mitigation Playbook

## Purpose

Detect, analyze, and mitigate a Distributed Denial-of-Service (DDoS) attack against a network service or infrastructure. Covers volumetric, protocol, and application-layer attacks; on-net and off-net mitigation; and customer communication.

## Audience

Network operators, SRE on-call, security architect, customer communications lead.

## Pre-conditions

1. The reference cards are current: `BGP_RFC_4271_VERSION_GOVERNANCE.md`, `RPKI_RFC_8210_VERSION_GOVERNANCE.md`, `MANRS_GOVERNANCE.md`.
2. The organization has an upstream provider with DDoS scrubbing.
3. The organization has a third-party DDoS scrubbing service (e.g., Cloudflare, AWS Shield Advanced, Akamai Prolexic).
4. The organization's network has RTBH (Remotely-Triggered Black Hole) capability.
5. The organization's network has flow telemetry (NetFlow, sFlow, IPFIX).

## Procedure

### 1. Detect

1. Monitor for:
   - Sustained increase in inbound traffic volume (> 2x baseline for 5+ minutes).
   - Spike in packets-per-second (> 1.5x baseline).
   - Spike in new TCP connections per second.
   - Spike in HTTP requests per second.
   - Spike in DNS query rate.
   - Resource exhaustion (CPU, memory, network).
2. Alert sources: SIEM, NOC monitoring, customer report, vendor alert.

### 2. Classify

1. Identify the attack vector:
   - **Volumetric**: UDP flood, ICMP flood, amplification (DNS, NTP, Memcached).
   - **Protocol**: SYN flood, Ping of Death, Smurf.
   - **Application**: HTTP flood, Slowloris, application-layer DDoS.
2. Identify the source:
   - Spoofed source IPs (anti-spoofing per RFC 8704).
   - Botnet IPs (intelligence feeds: Spamhaus, AbuseIPDB).
   - Single source / distributed.

### 3. Mitigate — volumetric

1. Enable upstream DDoS scrubbing (BGP diversion to the scrubbing center).
2. Apply RTBH for the targeted /32 (or more specific) prefix.
3. Apply FlowSpec rules to drop attack traffic at the edge.
4. Confirm attack traffic has dropped to baseline.
5. Communicate with the upstream provider.

### 4. Mitigate — protocol

1. Apply SYN cookies or SYN proxy at the edge.
2. Reduce SYN-ACK retransmit budget.
3. Apply rate-limiting at the per-source-IP level.
4. Validate application availability.

### 5. Mitigate — application

1. Apply rate-limiting at the application layer.
2. Apply CAPTCHA or challenge pages.
3. Use a WAF with application-layer DDoS rules.
4. Cache responses where possible.
5. Validate application availability.

### 6. Communicate

1. Internal: incident channel, status page (internal).
2. Customer-facing: status page, customer email.
3. Regulatory: per `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md`, notify if data is exfiltrated.
4. Law enforcement: per local regulations, notify for significant incidents.

### 7. Document

1. Open an incident ticket with:
   - Detection timestamp.
   - Attack vector classification.
   - Mitigation actions and timestamps.
   - Customer-impact assessment.
2. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md` for sustained attacks (> 1 hour).

### 8. Post-incident

1. Update DDoS runbook with lessons learned.
2. Update detection rules (SIEM, IDS/IPS).
3. Validate RTBH and FlowSpec are tested.
4. Schedule a tabletop exercise for the next quarter.

## Rollback

Rollback of a DDoS mitigation is the relaxation of the scrubbing / RTBH / FlowSpec rules. Rollback decisions:

- Customer impact from the mitigation exceeds the impact of the attack → relax the rules.
- Sustained attack → keep the rules.

## Mandatory pre-flight (before a high-traffic event)

1. Validate DDoS scrubbing contract is current.
2. Validate RTBH is configured.
3. Validate FlowSpec is configured.
4. Validate detection rules are current.
5. Tabletop exercise quarterly.

## References

- `BGP_RFC_4271_VERSION_GOVERNANCE.md`
- `ISO_IEC_27035_2016_INCIDENT_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- Cloudflare DDoS report: `https://radar.cloudflare.com/`
- AWS Shield Advanced: `https://aws.amazon.com/shield/`
- Akamai Prolexic: `https://www.akamai.com/our-thinking/ddos`
- NIST SP 800-61 Rev. 2: `https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final`
- RFC 8704 (BCP 84 update): `https://www.rfc-editor.org/rfc/rfc8704`
