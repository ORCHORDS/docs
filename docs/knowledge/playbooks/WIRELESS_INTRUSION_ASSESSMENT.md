---
title: "Wireless Intrusion Assessment"
owner: "Network Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
trigger: "Quarterly assessment, new wireless deployment, change in physical site or vendor, or post-incident when rogue access is suspected."
scope: "All corporate wireless networks, including production tenant Wi-Fi, guest networks, IoT segmentation networks, and operational technology Wi-Fi."
inputs:
  - "Authorized wireless inventory — SSIDs, BSSIDs, channels, controller identity"
  - "Site floor plans and physical boundaries"
  - "Recent wireless-related incidents or alerts"
  - "Authorized device list for managed Wi-Fi"
plan:
  - "Step 1: Confirm scope and physical site list for the assessment."
  - "Step 2: Walk each site with calibrated wireless sensors; record all observed SSIDs, BSSIDs, signal strength, encryption type, and channel."
  - "Step 3: Compare observed set against the authorized inventory; flag any unauthorized SSID or BSSID."
  - "Step 4: Test for evil-twin candidates — duplicate SSIDs with weaker encryption or unexpected channels."
  - "Step 5: Test for misconfigured authorized APs — WPA2-Personal in a corporate site, disabled management frame protection, or weak passphrases."
  - "Step 6: Validate segmentation — confirm IoT and OT SSIDs cannot reach corporate subnets."
  - "Step 7: Capture spectrum data and channel utilization to identify rogue APs and interference."
  - "Step 8: Report findings, isolate any rogue device, and capture residual actions."
evidence:
  - "Site walk report with observed SSID and BSSID inventory"
  - "Evil-twin and misconfiguration findings"
  - "Segmentation test results"
  - "Spectrum and channel utilization data"
  - "Residual action register"
escalation:
  - "Rogue AP with confirmed corporate traffic — escalate to Security on-call within 30 minutes."
  - "Segmentation failure between IoT or OT and corporate — escalate to Network Security leadership."
completion:
  - "Every site walked and observed set reconciled with authorized inventory."
  - "All rogues isolated or risk-accepted with compensating control."
exceptions:
  - "Sites with physical or regulatory constraints preventing walk testing; require alternative sensor placement."
related:
  - "PHYSICAL_ACCESS_REVIEW.md"
  - "NETWORK_SEGMENTATION_REVIEW.md"
  - "ASSET_INVENTORY_REVIEW.md"
