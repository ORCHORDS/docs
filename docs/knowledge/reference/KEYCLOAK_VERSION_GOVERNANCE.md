---
title: "Keycloak Identity and Access Management Version Governance"
owner: "Knowledge Engineering"
status: "approved"
classification: "public"
last-reviewed: "2026-09-08"
review-cycle: "180 days"
next-review: "2027-03-07"
source: "Keycloak project release notes and CNCF community guidance"
---

# Keycloak Identity and Access Management Version Governance

## Overview

Keycloak is a CNCF-governed open source identity and access management (IAM) service maintained by the Keycloak project under the Cloud Native Computing Foundation. The Quarkus-based distribution (Keycloak 17 and later, with Keycloak 26+ as the current generation) replaces the legacy WildFly server, delivering a cloud-native runtime with faster startup, lower memory footprint, and improved container ergonomics.

## Release Train

Keycloak follows a quarterly cadence for feature releases overlaid with a 6-monthly LTS (long-term support) tag on every second feature release. Each LTS line receives security and critical bug fixes for approximately twelve months; non-LTS releases are supported only until the next feature release. Production deployments should pin to the active LTS and apply patch releases within the support window.

## Core Concepts

A realm is the top-level tenant boundary. Within a realm, clients represent OAuth2/OIDC relying parties, roles partition application-level authorities at both realm and client scopes, and groups aggregate users for bulk assignment. Identity brokers link external IdPs as federated login sources.

## Protocol Endpoints

Keycloak exposes standard OIDC and OAuth 2.0/2.1 endpoints (authorization, token, JWKS, userinfo, end-session, introspection, revocation) and SAML 2.0 SP- and IdP-initiated flows. Token lifecycles include short-lived access tokens, long-lived refresh tokens with rotation, and ID tokens carrying user claims for OIDC relying parties.

## Administration

Configuration is exposed through the Admin REST API and the web-based Admin UI console. The Admin CLI (`kcadm.sh`) is the supported scriptable companion.

## Data and Authorization

Persistence relies on a single shared schema with vendor support for PostgreSQL (recommended), MariaDB, Oracle, and MSSQL. Authorization Services implement UMA 2.0 with resource servers defining fine-grained resources, scopes, and policies. Identity brokering supports social login providers (Google, GitHub, Facebook) and OIDC/SAML federations.

## Extensibility

Themes customize UI presentation. Service Provider Interfaces (SPIs) enable custom authenticators, protocol mappers, event listeners, and storage providers. On Kubernetes the Keycloak Operator manages realms, clients, and rollouts declaratively.

## Upgrade and Compatibility

Upgrades across LTS boundaries require schema migration and offline validation; the skip-releases policy permits moving within a single LTS lineage but not across. Compatibility horizon covers the current LTS, the previous LTS, and one feature release ahead of the next LTS. The version selection decision tree favors Quarkus over legacy WildFly, prefers the latest active LTS, selects PostgreSQL for primary support, and enables cluster mode for HA.

## Operational Impact

Operational impact points include database connection pooling, Infinispan cache sizing, realm export and import automation, and TLS certificate rotation.

## Cross-References

See [OIDC FAPI 2.0 Version Governance](OIDC_FAPI_2_VERSION_GOVERNANCE.md) and [OAuth 2.1 Version Governance](OAUTH_2_1_VERSION_GOVERNANCE.md) for the underlying protocol governance.

---

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
