# Threat Intelligence Consumption Playbook

## Purpose

Consume cyber threat intelligence (CTI) feeds end-to-end: ingest STIX 2.1 bundles over TAXII 2.1, normalize, deduplicate, enrich with internal context, score, and route to the SIEM, EDR, and SOAR.

## Audience

Threat intelligence analysts, SOC engineers, security architects.

## Pre-conditions

1. The reference cards are current: `RAVENSWORN_INDICATORS_GOVERNANCE.md`, `SIEM_ARCHITECTURE_GOVERNANCE.md`, `SOAR_AUTOMATION_GOVERNANCE.md`.
2. TAXII 2.1 collection is reachable.
3. STIX 2.1 ingest pipeline is in place.
4. Sharing-marking policy (TLP:RED/AMBER/GREEN/WHITE) is documented.
5. SIEM ingest endpoint is configured.

## Procedure

### 1. Discovery

1. Identify the TAXII 2.1 server URL.
2. Authenticate via OAuth 2.0 client credentials or API token.
3. Discover the API root: `GET /taxii2/`.
4. List collections: `GET /taxii2/<api_root>/collections/`.
5. Subscribe to the relevant collections.

### 2. Ingestion

1. Poll the manifest: `GET /taxii2/<api_root>/collections/<id>/manifest/`.
2. Fetch objects: `GET /taxii2/<api_root>/collections/<id>/objects/?added_after=<timestamp>`.
3. Validate STIX 2.1 schema.
4. Validate signing (if applicable).
5. Store in the CTI ingest database.

### 3. Normalization

1. Map STIX 2.1 SDOs / SROs to the internal schema (ECS or OCSF).
2. Extract indicators (file hashes, IPs, domains, URLs, emails).
3. Extract attack patterns (ATT&CK techniques).
4. Extract relationships (e.g., `indicator → indicates → malware`).

### 4. Deduplication

1. Deduplicate by:
   - Indicator value (hash, IP, domain).
   - Indicator type.
   - Source feed.
2. Merge duplicates into a single canonical indicator.
3. Track source feeds for each canonical indicator.

### 5. Enrichment

1. Enrich with internal context:
   - Internal asset ownership.
   - Internal ticket history.
   - Internal detection history.
2. Enrich with external sources:
   - VirusTotal (file hashes, domains, IPs).
   - Shodan (IP context).
   - GreyNoise (IP reputation).
   - Threat feeds: Spamhaus, AbuseIPDB.

### 6. Scoring

1. Score each indicator:
   - Source reputation (high for tier-1 intel, low for unknown).
   - Confidence (STIX `confidence` field).
   - Severity (CVSS if vulnerability, otherwise based on ATT&CK technique).
   - Internal relevance (does the indicator match internal assets).
2. Combined score determines priority:
   - High: actionable in 24 hours.
   - Medium: actionable in 7 days.
   - Low: archived.

### 7. Routing

1. Route to SIEM:
   - High-priority indicators become detection rules.
   - Medium-priority indicators are stored as searchable IOCs.
   - Low-priority indicators are archived.
2. Route to EDR:
   - File hashes → EDR file-blocking rules.
   - Domains → EDR DNS sinkhole rules.
3. Route to firewall:
   - IPs → firewall block rules.
   - Domains → DNS resolver block rules.
4. Route to SOAR:
   - High-priority indicators trigger SOAR playbooks (search for past activity).

### 8. Lifecycle

1. Indicator expiry:
   - File hashes: 30 days.
   - Domains: 90 days.
   - IPs: 30 days.
   - Vulnerabilities: until patched.
2. Indicators exceeding the expiry are removed from active rules.
3. Indicators exceeding the expiry are archived.

### 9. Observability

- Ingestion rate (counter, per feed).
- Ingestion latency p99 (histogram).
- Indicator count (gauge, by source).
- False-positive rate (per source).
- Time-to-action (per indicator).

### 10. Audit

1. Audit log captures: feed, indicator type, indicator value, source feed, score, action taken, timestamp.
2. Audit log retention: 1 year.
3. Audit log is immutable.

## Rollback

Rollback of CTI consumption actions:

- Action taken on indicator that turned out to be false positive → revert the action (unblock IP, unblock domain, etc.).
- Document the false positive in the CTI quality register.
- Provide feedback to the source feed (if feedback channel exists).

## Mandatory pre-flight (before adopting a new CTI feed)

1. Source reputation is documented.
2. Sharing-marking policy is documented.
3. Indicator types in use are documented.
4. Expiry policy is documented.
5. False-positive tracking is in place.

## References

- `RAVENSWORN_INDICATORS_GOVERNANCE.md`
- `SIEM_ARCHITECTURE_GOVERNANCE.md`
- `SOAR_AUTOMATION_GOVERNANCE.md`
- OASIS TAXII 2.1: `https://docs.oasis-open.org/cti/taxii/v2.1/taxii-v2.1.html`
- OASIS STIX 2.1: `https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html`
- MITRE ATT&CK: `https://attack.mitre.org/`
- FIRST Traffic Light Protocol (TLP): `https://www.first.org/tlp/`
