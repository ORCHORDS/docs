---
title: "API Gateway Threat Model Review"
owner: "Application Security"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
trigger: "New API gateway deployment, new gateway feature, new high-blast-radius API, or scheduled six-monthly review."
scope: "All production API gateway deployments and all APIs served through them."
inputs:
  - "API gateway inventory with route map"
  - "API specifications and authentication configuration"
  - "Rate limiting, quota, and throttling configuration"
  - "Recent incidents and threat intelligence"
plan:
  - "Step 1: Confirm scope and pull API gateway inventory with route map."
  - "Step 2: Validate authentication and authorization configuration for every route, including token validation, scope enforcement, and audience checks."
  - "Step 3: Validate rate limiting, quota, and throttling configuration against the documented policy; flag any route without limits."
  - "Step 4: Validate input validation, schema enforcement, and request size limits at the gateway."
  - "Step 5: Validate response handling: data classification, sensitive data filtering, and error response normalization."
  - "Step 6: Threat model the gateway configuration: identify abuse paths, bypass paths, and integration risks with downstream services."
  - "Step 7: Document residual risks and route them through the standard risk acceptance workflow."
evidence:
  - "API gateway inventory and route map"
  - "Authentication and authorization configuration exports"
  - "Rate limiting and quota configuration exports"
  - "Threat model with abuse and bypass paths"
  - "Residual risk register entries"
escalation:
  - "Any route without authentication or rate limits — escalate to Application Security."
  - "Any documented abuse path with active exploitation — escalate to Security on-call."
completion:
  - "Every route has documented authentication, authorization, and rate limits."
  - "Threat model signed off by Application Security."
exceptions:
  - "Routes explicitly approved for anonymous or unauthenticated access; documented in the API gateway policy."
related:
  - "THREAT_MODEL_REVIEW.md"
  - "ACCESS_REVIEW.md"
  - "INCIDENT_COMMUNICATIONS_REVIEW.md"
