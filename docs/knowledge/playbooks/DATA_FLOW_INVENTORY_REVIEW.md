# Data-Flow Inventory Review

## Trigger

Run periodically and when new integrations, processors, storage locations, product features, analytics paths, or data-sharing arrangements materially change processing.

## Inputs

- Current data inventory
- Architecture / integration map
- Vendor and processor inventory
- Data retention and privacy records
- Product/service documentation

## Procedure

1. Identify systems, products, and services that process data.
2. Confirm owners/operators and relevant third parties.
3. Inventory the data elements, data actions, processing purposes, and environments involved.
4. Trace material data flows between components, storage systems, users, and third parties.
5. Compare the documented map with current integrations, exports, queues, APIs, analytics, backups, and processors.
6. Identify undocumented, obsolete, unnecessary, or unexpectedly broad flows.
7. Assign remediation for material gaps and update the canonical inventory/map.
8. Preserve review evidence, decisions, and the next review date.

## Escalation

Escalate flows involving sensitive data, unknown processors, unexpected cross-border processing, undocumented exports, or processing with no clear business purpose.

## Completion criteria

- Material processing paths are represented.
- Owners/operators and third parties are identified.
- Data elements, actions, purposes, and environments are current.
- Material discrepancies have owners and deadlines.

## Source basis

- NIST Privacy Framework — Inventory and Mapping (ID.IM-P)
