> Auto-generated from `Api Contract.md` in the docs repo.

> Auto-generated from `Api Contract.md` in the docs repo.

> Auto-generated from `Api Contract.md` in the docs repo.

> Auto-generated from `docs/backend/API_CONTRACT.md` in the docs repo.

---
title: "Backend API Contract"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# Backend API Contract

**Project:** Beetle Studio  
**Owner:** Maya Rodriguez (Senior Backend Developer)  
**Reviewers:** Kirk Beka (CTO), Chris Taylor (Product Manager)  
**ISO Standards:** ISO/IEC 12207:2017 (development, interfaces), ISO/IEC 27001:2022 (security), ISO/IEC 25010:2023 (functional suitability, compatibility)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Firebase API endpoints, auth flow, and sync protocol |
| **Diátaxis form** | Reference |
| **Primary audience** | Maya Rodriguez, Kirk Beka, Chris Taylor, all client engineers |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines the API contract between the Beetle Studio desktop application and the Firebase backend services. Per **ISO/IEC 12207:2017 section 6.1**, API specifications must be stable and versioned so that changes don't break existing clients. Per **ISO/IEC 27001:2022**, security controls must be embedded in API design.
## Contents

- [Technology Stack](#technology-stack)
- [Authentication Flow](#authentication-flow)
  - [Token Management](#token-management)
- [Firestore Data Model](#firestore-data-model)
  - [Collections](#collections)
  - [Security Rules](#security-rules)
- [API Endpoints (Cloud Functions)](#api-endpoints-cloud-functions)
  - [Project Sync](#project-sync)
  - [License Validation](#license-validation)
  - [Analytics Event](#analytics-event)
- [Versioning Policy](#versioning-policy)
  - [Breaking Change Process](#breaking-change-process)
- [Security Requirements](#security-requirements)
- [Firebase Security Rules](#firebase-security-rules)
  - [Rule Files](#rule-files)
  - [Core Rule Patterns](#core-rule-patterns)
  - [Required Rule Checks (OWASP ASVS mapping)](#required-rule-checks-owasp-asvs-mapping)
  - [Rule Testing](#rule-testing)
  - [Deployment](#deployment)
  - [Rule Change Process (per ISO/IEC 14764:2022)](#rule-change-process-per-isoiec-147642022)
  - [Firebase Auth Configuration](#firebase-auth-configuration)
  - [Cloud Functions Security](#cloud-functions-security)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| **Auth** | Firebase Authentication | Email/password, Google OAuth, future SSO |
| **Database** | Firestore | Real-time sync, offline-first |
| **Cloud Functions** | Firebase Cloud Functions | Business logic, API endpoints |
| **Storage** | Firebase Storage | Project assets, cloud sync |
| **Hosting** | Firebase Hosting | Static assets, web components |

---

## Authentication Flow

```
┌──────────────────────────────────────────────────────┐
│           BEETLE STUDIO → FIREBASE AUTH             │
│                                                       │
│  1. App starts → check FirebaseAuth.instance        │
│                      │                              │
│                      ▼                              │
│              Is user logged in?                     │
│               │           │                        │
│            Yes            No                        │
│               │           │                        │
│               ▼           ▼                        │
│        Load user      Show login UI                 │
│        profile        (FirebaseUI)                  │
│               │                                       │
│               ▼                                       │
│        Sync projects + settings                       │
└──────────────────────────────────────────────────────┘
```

### Token Management

| Token | Lifetime | Storage | Refresh |
|---|---|---|---|
| **ID Token** | 1 hour | Secure storage (Windows Credential Manager) | Auto-refreshed by SDK |
| **Refresh Token** | Never expires (until revoked) | Encrypted in local config | Used to get new ID token |

---

## Firestore Data Model

### Collections

```
users/{userId}/
  email: string
  displayName: string
  createdAt: timestamp
  lastLoginAt: timestamp
  plan: "free" | "pro" | "enterprise"
  
users/{userId}/projects/{projectId}/
  name: string
  createdAt: timestamp
  updatedAt: timestamp
  thumbnailUrl: string | null
  cloudStatus: "synced" | "local-only" | "conflict"
  settings: map

users/{userId}/projects/{projectId}/assets/{assetId}/
  filename: string
  sizeBytes: number
  storagePath: string
  uploadedAt: timestamp
```

### Security Rules

```javascript
// Firestore security rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      // Users can only read/write their own data
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    match /users/{userId}/projects/{projectId} {
      allow read: if request.auth != null && request.auth.uid == userId;
      allow write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

---

## API Endpoints (Cloud Functions)

### Project Sync

```
POST /api/v1/sync
  Auth: Bearer {ID token}
  Body: { lastSyncTimestamp: number, projectId: string }
  Response: { changes: ProjectChange[], newAssetUrls: AssetRef[] }
  Error: 401 Unauthorized, 403 Forbidden, 429 Rate Limited
```

### License Validation

```
POST /api/v1/license/validate
  Auth: Bearer {ID token}
  Body: { licenseKey: string }
  Response: { valid: boolean, plan: string, expiresAt: number }
  Error: 401 Unauthorized, 400 Invalid Key
```

### Analytics Event

```
POST /api/v1/analytics/event
  Auth: Bearer {ID token}
  Body: { eventName: string, properties: map, timestamp: number }
  Note: Opt-in only; user must consent to analytics
```

---

## Versioning Policy

| Change Type | Version Bump | CI/CD Action |
|---|---|---|
| Add new endpoint | None | Deploy immediately |
| Add optional parameter | None | Deploy immediately |
| Add required parameter | MAJOR | Notify clients; 6-month deprecation window |
| Remove endpoint | MAJOR | 6-month deprecation notice |
| Change response shape | MAJOR | 6-month deprecation; new endpoint |

### Breaking Change Process

1. Announce deprecation in changelog and Firebase console
2. Old endpoint returns `Deprecation-Warning` header
3. After 6 months: old endpoint returns `410 Gone`
4. After 12 months: old endpoint removed

---

## Security Requirements

Per **ISO/IEC 27001:2022 Annex A**, the API must:

- [ ] Authenticate all requests with a valid Firebase ID token
- [ ] Validate all input data server-side (never trust client)
- [ ] Rate limit all endpoints (Cloud Functions + Firestore)
- [ ] Log all authentication failures
- [ ] Encrypt data at rest (Firestore default) and in transit (HTTPS/TLS)
- [ ] Never expose internal error details to clients

---

## Firebase Security Rules

Firebase Security Rules are the primary security control for our Firestore data and Storage. Rules are **version-controlled** in the repo, **deployed via CI/CD**, and **tested with the Firebase Emulator Suite** before any production change.

### Rule Files

| File | Protects |
|---|---|
| `firestore.rules` | All Firestore collections |
| `storage.rules` | All Cloud Storage buckets (user assets, exports) |
| `apphosting.rules` | App Hosting resources (if used) |

### Core Rule Patterns

**User can only read/write their own data:**

```javascript
match /users/{userId} {
  allow read, write: if request.auth != null && request.auth.uid == userId;
}
```

**Project access via ACL field:**

```javascript
match /projects/{projectId} {
  allow read: if request.auth != null
    && (resource.data.ownerId == request.auth.uid
        || request.auth.uid in resource.data.collaborators);
  allow write: if request.auth != null
    && resource.data.ownerId == request.auth.uid;
}
```

**Rate-limit at the rule level** (Firestore limits + custom counters in a separate collection).

### Required Rule Checks (OWASP ASVS mapping)

| Check | Where | ASVS Reference |
|---|---|---|
| Authentication required for any non-public read | All `match` blocks | V2.1, V8 |
| Auth.uid matches resource ownerId | All per-user collections | V4.1 |
| Input validation on writes (string length, type) | `request.resource.data` | V5.1 |
| No PII in document IDs | Schema review | V9 |
| No client-side trust on role/admin claims | Server-only token verification | V4.2 |
| Time-based document expiry for temp uploads | `expirationTime` field | V13 |

### Rule Testing

- **Firebase Emulator Suite** runs locally; unit tests in `tests/rules/*.test.ts`
- **Coverage requirement:** every `match` block has at least one positive + one negative test
- **CI gate:** rules tests must pass before deploy (see [CI_CD_PIPELINE.md](../engineering/CI_CD_PIPELINE.md))

### Deployment

| Command | Effect |
|---|---|
| `firebase deploy --only firestore:rules` | Push rules to production |
| `firebase deploy --only storage` | Push storage rules |
| `firebase emulators:exec --only firestore,storage "npm test"` | Local rule tests |

### Rule Change Process (per ISO/IEC 14764:2022)

1. PR opened with rule diff + test diff
2. Code review by `Maya Rodriguez (Backend)` or `Kirk Beka (CTO)`
3. CI runs rule tests in emulator
4. Canary deploy to staging project
5. Manual smoke test in staging
6. Promote to production

### Firebase Auth Configuration

| Setting | Value | Standard |
|---|---|---|
| **Min password length** | 12 characters | ASVS V2.1, NIST SP 800-63B |
| **MFA required for** | All admin users, all users with active subscription | ISO 27002 A.5.17 |
| **Session duration** | 1 hour (web), 30 days (desktop, refresh token rotation) | ISO 27002 A.5.18 |
| **Email enumeration** | Blocked (same response for unknown email) | ASVS V2.2 |
| **Token signing keys** | Auto-rotated by Google | ISO 27002 A.8.24 |
| **Custom claims** | Used for `isAdmin`, `planTier`; validated server-side | ASVS V4.2 |

### Cloud Functions Security

| Control | Implementation |
|---|---|
| **Auth required** | Every callable function starts with `if (!context.auth) throw ...` |
| **Input validation** | Zod schema validation at function entry |
| **Secrets** | Google Secret Manager, never in env vars |
| **CORS** | Restricted to `mooned.dev` and `www.mooned.dev` |
| **Rate limiting** | Firebase App Check + per-user counter in Firestore |
| **App Check** | Required for all production traffic (blocks unauthenticated API access) |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial contract — aligned with ISO/IEC 12207:2017 §6.1, ISO/IEC 27001:2022 |

---

*Grounded in: ISO/IEC 12207:2017 §6.1 (Design), ISO/IEC 27001:2022 Annex A, ISO/IEC 25010:2023*



---

## References

### Internal Documents

- [$title](./../engineering/CI_CD_PIPELINE.md)

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Maya Rodriguez | Initial version |
| 1.0.1 | June 2026 | Maya Rodriguez | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** On API breaking change
- **Reviewer:** Maya Rodriguez (Senior Backend Developer)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type