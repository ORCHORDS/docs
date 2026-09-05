# PeeringDB and IRR Database Update Playbook

## Purpose

Maintain accurate, current routing information in PeeringDB, the Internet Routing Registry (IRR), and the RPKI repository. The playbook covers the day-2 maintenance of these databases, which are mandatory inputs to the BGP reference architecture and MANRS conformance.

## Audience

Network operators, BGP engineers, peering coordinators.

## Pre-conditions

1. The reference cards are current: `BGP_RFC_4271_VERSION_GOVERNANCE.md`, `RPKI_RFC_8210_VERSION_GOVERNANCE.md`, `MANRS_GOVERNANCE.md`.
2. The organization has accounts on:
   - PeeringDB (`https://www.peeringdb.com/`)
   - One or more IRR databases: RIPE, ARIN, APNIC, NTTCOM, RADB.
3. The organization has an RPKI dashboard account (per `RPKI_DEPLOYMENT_PLAYBOOK.md`).

## Procedure

### 1. PeeringDB maintenance

1. Update the organization's PeeringDB record on every change to:
   - ASN (rare).
   - NOC contacts.
   - Peering policy (open, selective, restrictive).
   - Network facilities (colo locations).
   - Network type (NSP, Content, Enterprise, Educational, etc.).
   - Traffic statistics (low/medium/high).
2. Add peering sessions when new interconnections are deployed.
3. Remove peering sessions when decommissioned.
4. Validate the PeeringDB record is reachable from `https://www.peeringdb.com/`.
5. Document the change in the change ticket.

### 2. RIPE database maintenance (if applicable)

1. Maintain the `aut-num` object with current routing policy.
2. Maintain the `as-set` object with current peer list.
3. Maintain the `route` and `route6` objects for each originated prefix.
4. Maintain the `mp-export` and `mp-import` objects for AS-Path and prefix filters.
5. Validate the database objects are well-formed (use `RIPE whois` or `whois.ripe.net`).
6. Document the change.

### 3. ARIN database maintenance (if applicable)

1. Maintain ARIN Online records for routing policy.
2. Maintain the customer reconciliation (CR) records.
3. Validate the records are current.

### 4. APNIC database maintenance (if applicable)

1. Maintain APNIC Whois records.
2. Maintain IRR records at APNIC.
3. Validate the records are current.

### 5. NTTCOM / RADB database maintenance

1. Maintain IRR records in NTTCOM, RADB, and other third-party databases.
2. Validate the records are consistent across databases.

### 6. RPKI ROA maintenance

1. Add a ROA when a new prefix is allocated.
2. Update a ROA when max-length or origin ASN changes.
3. Remove a ROA when a prefix is no longer originated.
4. Validate the ROA is visible in the validator cache within 5 minutes.

### 7. Consistency checks

1. Validate the ASN, prefix, and origin ASN are consistent across:
   - PeeringDB record.
   - RIPE/ARIN/APNIC IRR records.
   - Third-party IRR records (NTTCOM, RADB).
   - RPKI ROA records.
2. Validate that all originated prefixes have a ROA.
3. Validate that all ROAs match the actual BGP announcements.
4. Document inconsistencies in the change ticket.

### 8. Cadence

1. **Daily**: monitor for stale records (via PeeringDB validation API).
2. **Weekly**: validate ROA coverage for all originated prefixes.
3. **Monthly**: validate IRR records against BGP announcements.
4. **On change**: update PeeringDB, IRR, and ROA together.
5. **Annually**: full review of routing policy and IRR records.

## Rollback

Rollback of an IRR / PeeringDB / ROA change is possible only if the change has not yet propagated to upstream providers. After propagation, rollback is not possible without coordinated upstream action.

Rollback procedure:

1. Identify the change that introduced the issue.
2. Revert the change in PeeringDB, IRR, and ROA.
3. Validate BGP connectivity.
4. Notify upstream providers if necessary.
5. Trigger `INCIDENT_POSTMORTEM_REVIEW_PLAYBOOK.md`.

## References

- `BGP_RFC_4271_VERSION_GOVERNANCE.md`
- `RPKI_RFC_8210_VERSION_GOVERNANCE.md`
- `RPKI_DEPLOYMENT_PLAYBOOK.md`
- `MANRS_GOVERNANCE.md`
- PeeringDB: `https://www.peeringdb.com/`
- RIPE Database: `https://apps.db.ripe.net/`
- ARIN Whois: `https://www.arin.net/resources/registry/whois/`
- APNIC Whois: `https://wq.apnic.net/whois-search/static/search.html`
- RADB: `https://www.radb.net/`
- NTTCOM IRR: `https://www.ntt.net/products/rr/`
