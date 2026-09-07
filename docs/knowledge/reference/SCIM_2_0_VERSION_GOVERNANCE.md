---
title: "SCIM 2.0 Identity Provisioning Protocol Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "IETF SCIM v2.0 (RFC 7642, RFC 7643, RFC 7644) and SCIM Working Group drafts"
---

# SCIM 2.0 Identity Provisioning Protocol Version Governance

## System for Cross-Domain Identity Management (SCIM) version 2.0

SCIM 2.0 is the IETF-standardized provisioning protocol defined in RFC 7642 (conceptual model), RFC 7643 (core schema), and RFC 7644 (protocol). It supersedes the vendor-led SCIM 1.1 draft and provides a stable, interoperable contract for moving identity state between identity providers and downstream applications.

## Core Schema, Resource Types, and Extensions

The canonical resource types are `User` and `Group`, with `EnterpriseUser` defined as a schema extension that adds workplace attributes such as `employeeNumber`, `department`, `costCenter`, and `manager`. Implementations MAY publish additional schema URIs and advertise them through the `/Schemas` endpoint, preserving forward compatibility while remaining strictly typed.

## HTTP REST API for Provisioning

Provisioning and deprovisioning are modeled as REST operations against JSON resources. POST creates, GET retrieves, PUT replaces, PATCH updates incrementally, and DELETE removes. Each operation returns the affected resource representation and a status code drawn from RFC 7231.

## Endpoints

The six normative endpoints are `/Users`, `/Groups`, `/ServiceProviderConfig`, `/Schemas`, `/Bulk`, and `/Me`. `/ServiceProviderConfig` advertises supported features; `/Schemas` exposes attribute definitions; `/Me` permits authenticated end-user self-service.

## Filtering, Pagination, Sorting, Attribute Selection

RFC 7644 Section 3.4.2.2 defines filter operators (`eq`, `ne`, `co`, `sw`, `pr`, `gt`, `ge`, `lt`, `le`, `and`, `or`, `not`). Pagination uses `startIndex` and `count`; sorting uses `sortBy` and `sortOrder`; attribute selection uses `attributes` and `excludedAttributes`. Clients SHOULD respect server-advertised limits.

## PATCH Operations

Incremental updates use JSON Patch operations (`add`, `remove`, `replace`) within an `Operations` array. PATCH is preferred over PUT for partial changes because it preserves server-managed attributes such as `meta.created`.

## Bulk Operations

`/Bulk` accepts up to `maxOperations=1000` requests per call as specified in RFC 7644 Section 3.7. Each operation carries a `bulkId` so the client can correlate failures in the aggregated `Errors` response.

## ETags for Optimistic Concurrency

ETags returned in the `ETag` response header and `meta.version` field prevent lost updates. Clients reissue writes with `If-Match` to detect concurrent modification.

## Authentication and Transport

SCIM requires TLS for transport confidentiality. Authentication is typically OAuth 2.0 bearer tokens; basic auth and mutual TLS remain acceptable for trusted integrations. The `/Me` endpoint requires an end-user-scoped token.

## SAML/OIDC Integration Patterns

SCIM is layered over an IdP. SAML or OIDC handles authentication, while SCIM handles lifecycle provisioning. The IdP pushes deltas to the SCIM server, which fans them out to applications.

## Operational Profiles

Okta, Microsoft Entra ID, Google Workspace, Auth0, and Keycloak each ship SCIM 2.0 clients or servers with documented deviations from RFC 7644, primarily around filter dialect, bulk sizing, and extension schemas.

## Version Selection Decision Tree

Single-tenant deployments select SCIM 2.0 with the `EnterpriseUser` extension and PATCH. Multi-tenant deployments additionally require custom schemas per tenant and bulk operations for initial seeding. Per-resource PATCH is preferred thereafter.

## Compatibility Horizon

SCIM 1.1 is deprecated. SCIM 2.0 is the baseline. New integrations MUST target 2.0; legacy bridges are limited to 24 months of maintenance support.

## Operational Impact Points

Rate limiting per RFC 6585, HTTP 409 conflict resolution via ETag retry, and soft-delete semantics (`active=false`) replace hard deletes to preserve audit trails.

## Cross-references

- RFC 7642 conceptual model
- RFC 7643 core schema
- RFC 7644 protocol

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
