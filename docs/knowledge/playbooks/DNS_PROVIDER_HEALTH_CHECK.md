---
title: "DNS Provider Health Check"
owner: "Network Operations"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "30 days"
next-review: "2026-10-05"
trigger: "Monthly health check, new authoritative zone, DNS provider change, or DNS-related incident."
scope: "All authoritative and recursive DNS configurations used for production and corporate traffic, including public zones, split-horizon zones, and resolver configuration."
inputs:
  - "Zone inventory across providers"
  - "Provider service health feeds"
  - "DNSSEC configuration and key state"
  - "Resolver and forwarder configuration"
  - "Recent DNS-related incidents or anomalies"
plan:
  - "Step 1: Confirm scope — list every authoritative zone and every recursive resolver configuration."
  - "Step 2: Verify provider service health from the authoritative source; record outages and degradations since the last check."
  - "Step 3: Verify SOA records, NS records, and delegation for every authoritative zone."
  - "Step 4: Verify DNSSEC chain of trust for signed zones; confirm DS records match and signatures are within their validity window."
  - "Step 5: Verify resolver configuration against the documented policy: upstream resolvers, forwarding targets, DNSSEC validation, and TLS for resolver-to-upstream where configured."
  - "Step 6: Verify TTL strategy: short enough for failover but not so short as to amplify client-side failure modes."
  - "Step 7: Document residual actions for any finding; open remediation tickets with owners and deadlines."
evidence:
  - "Zone and resolver inventory snapshots"
  - "DNSSEC chain verification output"
  - "Provider health feed extracts"
  - "TTL configuration table"
  - "Residual action register"
escalation:
  - "DNSSEC chain failure or signature expiration — escalate to Network Operations leadership."
  - "Resolver forwarding to unauthorized upstream — escalate to Security."
completion:
  - "Every authoritative zone verified."
  - "Every resolver configuration verified against policy."
  - "DNSSEC chain healthy for every signed zone."
exceptions:
  - "Zones delegated to a third party with documented contractual responsibility."
related:
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
  - "NETWORK_SEGMENTATION_REVIEW.md"
  - "CHANGE_CONTROL.md"
