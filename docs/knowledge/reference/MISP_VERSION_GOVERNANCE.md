---
title: "MISP Threat Intelligence Platform Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "MISP Project (CIRCL) release notes and MISP Galaxy documentation"
---

# MISP Threat Intelligence Platform Version Governance

## Overview
MISP (Malware Information Sharing Platform) is an open-source threat intelligence platform maintained by CIRCL.LU (Computer Incident Response Center Luxembourg). The platform enables structured sharing, correlation, and analysis of Indicators of Compromise (IoCs) across organisations and communities. This governance card documents supported versions, data model semantics, and selection criteria for MISP deployments.

## Core Data Model
The MISP data model comprises Event (top-level container), Attribute (IoC values with type and category), Object (composite structures), Galaxy (threat-actor and malware knowledge clusters), Tag (free-form labels), Taxonomy (controlled vocabularies), Warninglist (allow/deny lists), and Correlation (engine results). See `docs/knowledge/reference/MISP_DATA_MODEL.md:1` for full semantics.

## API and Feed Distribution
MISP exposes a REST API consumed by PyMISP clients (Python) and misp-stix bridges. Feeds are distributed as GZIP-compressed, GPG-signed JSON archives fetched by remote servers and clients.

## User Roles
Six RBAC roles govern permissions: Site Admin (global), Org Admin (organisation), Admin (event management), User (read/contribute), Publisher (release to communities), Sync User (server-to-server only).

## Sharing Communities
Three topologies are supported: client-server (single MISP instance with remote users), server-to-server sync (peer MISP instances exchanging events), and feed distribution (signed GZIP feeds to consumers).

## Taxonomy and Galaxy Support
MISP Taxonomies provide controlled tagging primitives (advisory, classification, MITRE ATT&CK). MISP Galaxies encode encyclopaedic clusters (threat actors, software, tools). Both are versioned independently of the core platform.

## Correlation Engine
The correlation engine performs value-vs-value matching against stored Attributes and applies rule-based triggers (regex, hash, frequency). Correlation exclusions use Warninglists to reduce false positives.

## Authentication
Authentication uses per-user API keys for REST access and passphrases to unlock PGP-signed zips containing feed material and exports.

## STIX Interoperability
STIX 2.x export/import is provided by the misp-stix library, mapping Events to STIX bundles and back with fidelity loss documented per object type.

## Ecosystem Integrations
MISP integrates with TheHive (case management), Cortex (analysis responders), and OpenCTI (knowledge graph) via dedicated PyMISP connectors.

## Compatibility Horizon
MISP 2.4.x is the current production major line. 2.5 is in limited release; LTS branches receive security backports for 12 months.

## Version Selection Decision Tree
- Single instance with light sharing: install 2.4.x latest patch; default retention 1 year.
- Multi-server sync with federation: deploy identical 2.4.x versions; align feed and Galaxy revisions.
- High-retention (>3 years) environments: pin LTS branch and disable auto-upgrade of Galaxy clusters.

## Operational Impact Points
Schema migrations occur between minor versions. Taxonomies and Galaxies must be refreshed independently after upgrade. Feed consumers must re-validate GPG signatures against the rotated CIRCL key.

## Cross-References
- `docs/knowledge/reference/MISP_DATA_MODEL.md:1`
- `docs/knowledge/reference/PYMISP_CLIENT_GUIDE.md:1`
- `docs/knowledge/reference/STIX_INTEROP_MATRIX.md:1`
- `docs/knowledge/reference/THEHIVE_CORTEX_BRIDGE.md:1`

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.