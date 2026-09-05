# RPKI Deployment and ROV Activation Playbook

## Purpose

Deploy RPKI for an organization's prefixes and enable Route Origin Validation (ROV) on the organization's BGP routers, end-to-end. The playbook covers ROA publication, validator cache setup, RPKI to Router session, ROV activation, and operational monitoring.

## Audience

Network operators, BGP engineers, security architect, SRE.

## Pre-conditions

1. The reference cards are current: `RPKI_RFC_8210_VERSION_GOVERNANCE.md`, `BGP_RFC_4271_VERSION_GOVERNANCE.md`, `MANRS_GOVERNANCE.md`.
2. The organization has its prefixes and ASNs allocated from a regional RIR.
3. The organization has a BGP edge with at least one upstream transit provider.
4. The RIR's RPKI dashboard account is provisioned.

## Procedure

### 1. ROA publication

1. Log into the RIR's RPKI dashboard (e.g., ARIN, RIPE, APNIC, LACNIC, AFRINIC).
2. For each prefix the organization originates, create a ROA with:
   - `prefix`: the IP prefix (e.g., 192.0.2.0/24).
   - `maxLength`: the longest prefix that may be originated (typically /24 for IPv4, /48 for IPv6).
   - `origin ASN`: the AS number that originates the prefix.
3. Sign the ROA with the RIR-issued CA.
4. Publish the ROA to the RIR's publication point.
5. Validate the ROA is visible in the validator cache within 5 minutes.
6. Document the ROA in the project's ROA inventory.

### 2. Validator cache setup

1. Deploy a validator cache. Recommended options:
   - **Routinator** (NLnet Labs, Rust)
   - **FORT validator** (NIC Mexico, Go)
   - **RPSTI** validator (RIPE NCC)
   - **OctoRPKI** (Cloudflare, Go)
2. Configure the validator cache with the five RIR trust anchors (ARIN, RIPE, APNIC, LACNIC, AFRINIC).
3. Run `rsync` from each RIR's publication repository:
   - `rsync://rpki.arin.net/repository/`
   - `rsync://rpki.ripe.net/repository/`
   - `rsync://rpki.apnic.net/repository/`
   - `rsync://rpki.lacnic.net/repository/`
   - `rsync://rpki.afrinic.net/repository/`
4. Validate the validator cache is reachable from the BGP edge.
5. Document the cache endpoint URL.

### 3. RPKI to Router protocol

1. Configure the BGP router to act as a RPKI-Router client (RFC 8210).
2. Default port: 323.
3. Configure SSH or TCP/TLS to the validator cache.
4. Validate the session is established.
5. Validate the router receives ROA payloads.
6. Document the session in the network operations diagram.

### 4. ROV activation

1. Enable ROV on every eBGP session.
2. Configure the validation policy (per `RPKI_RFC_8210_VERSION_GOVERNANCE.md`):
   - `Valid` → accept
   - `Invalid` → reject
   - `NotFound` → accept (default permissive) or reject (strict)
3. Validate the policy does not block legitimate prefixes (the organization has published ROAs for all prefixes).
4. Validate the policy rejects invalid prefixes (use a test prefix).
5. Document the policy.

### 5. Validation scenarios

1. **Valid scenario**: originate a prefix with a matching ROA → BGP session accepts.
2. **Invalid scenario**: originate a prefix with a mismatched origin ASN → BGP session rejects (with `RPKI_INVALID` reason).
3. **NotFound scenario**: originate a prefix with no ROA → BGP session accepts (with permissive policy).
4. **ROA removed**: remove a ROA → BGP session transitions from `Valid` to `NotFound`.

### 6. Observability

- RPKI cache freshness (per RIR TA).
- Validated ROA count (gauge).
- RPKI validator query rate.
- BGP ROV state distribution: Valid, Invalid, NotFound (counters).
- BGP ROV rejections (counter, per reason).
- RPKI to Router session health.

### 7. Operational monitoring

1. Monitor RPKI cache freshness; alert on stale cache (≥ 5 minutes).
2. Monitor ROA coverage for the organization's prefixes; alert on missing ROAs.
3. Monitor ROV rejections; alert on sustained increase (could indicate attack or ROA misalignment).
4. Document the operational runbook for ROV-related incidents.

## Rollback

Rollback decisions:

- Sustained ROV rejections → investigate before reverting.
- BGP session failures → validate ROAs; rollback only if confirmed misconfiguration.
- RPKI cache outage → disable ROV temporarily; alert the on-call.

Rollback procedure:

1. Disable ROV on the affected session.
2. Validate BGP connectivity.
3. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `RPKI_RFC_8210_VERSION_GOVERNANCE.md`
- `BGP_RFC_4271_VERSION_GOVERNANCE.md`
- `MANRS_GOVERNANCE.md`
- `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`
- RPKI Validator implementations: `https://www.nlnetlabs.nl/projects/rpki/`, `https://github.com/NICMx/FORT-validator`
- RPKI to Router Protocol: `https://www.rfc-editor.org/rfc/rfc8210`
- MANRS: `https://www.manrs.org/`
