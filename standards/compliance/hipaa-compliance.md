# hipaa-compliance

**Issue:** HIPAA — PHI, BAA, security rule
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a health app. You store user health data. You
don't sign a BAA with your cloud vendor. You have a
breach. The OCR fines you $1.5M.

## Root cause
**HIPAA applies to PHI.** Sign a BAA + follow the
Security Rule.

**Source:** HHS HIPAA:
https://www.hhs.gov/hipaa/

## The "PHI" concept

PHI (Protected Health Information) is individually
identifiable health info:
- **Names**
- **Dates** (birth, admission, discharge, death)
- **Phone, fax, email, SSN, MRN, etc.**
- **Photos**
- **Health info** linked to the above

PHI must be protected.

## The "BAA" pattern

For a BAA (Business Associate Agreement):
- **Sign with:** Cloud vendor, payment processor, any
  vendor that touches PHI
- **Defines:** Responsibilities for PHI

```markdown
This BAA between [Provider] and [Vendor] sets forth
the terms by which [Vendor] will handle PHI on behalf
of [Provider].
```

The BAA is signed before any PHI is shared.

## The "Security Rule" pattern

For the Security Rule (45 CFR 164.302-318):
- **Administrative:** Policies, training, risk
- **Physical:** Facility access, workstation
- **Technical:** Access control, audit, encryption

The Security Rule is comprehensive.

## The "technical safeguards" pattern

For technical safeguards:
- **Access control:** Unique user IDs, emergency access,
  encryption, auto-logoff
- **Audit controls:** Hardware, software, procedural
- **Integrity:** Protect from improper alteration
- **Person authentication:** Verify the person
- **Transmission security:** Encrypt in transit

```ts
// Auto-logoff
response.headers.set('Cache-Control', 'no-store, no-cache, must-revalidate');
```

The safeguards are implemented.

## The "encryption" pattern

For encryption:
- **At rest:** AES-256
- **In transit:** TLS 1.2+
- **Keys:** Managed separately

```ts
import { encrypt, decrypt } from './crypto';

const encrypted = await encrypt(phi, encryptionKey);
await env.DB!.prepare(`INSERT INTO health_records (id, data) VALUES (?, ?)`).bind(id, encrypted).run();
```

The PHI is encrypted at rest.

## The "access control" pattern

For access control:
- **Role-based:** Doctor, nurse, admin
- **Need-to-know:** Only what's needed
- **Audit:** Every access is logged

```sql
CREATE TABLE access_log (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  patient_id TEXT NOT NULL,
  action TEXT NOT NULL,  -- 'view', 'edit', 'export'
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The access is logged.

## The "minimum necessary" pattern

For minimum necessary:
- **Don't:** Show all data
- **Do:** Show only what's needed for the task

```ts
// Doctor sees full chart
// Nurse sees medication list
// Receptionist sees name + appointment
```

The data is scoped.

## The "breach notification" pattern

For breach notification:
- **60 days:** Notify affected individuals
- **60 days:** Notify HHS (for 500+ individuals)
- **Immediately:** Notify media (for 500+ in a state)

**Source:** HHS Breach Notification Rule:
https://www.hhs.gov/hipaa/for-professionals/breach-notification/

## The "risk assessment" pattern

For a risk assessment (required):
- **Asset inventory:** What data do you have?
- **Threats:** What could happen?
- **Vulnerabilities:** What weaknesses?
- **Likelihood:** How likely?
- **Impact:** How bad?

The risk assessment is annual.

## The "training" pattern

For training:
- **Annual:** All workforce
- **New hires:** Within 30 days
- **Policy changes:** Within 30 days

The training is documented.

## The "contingency plan" pattern

For a contingency plan:
- **Data backup:** Regular
- **Disaster recovery:** Plan + test
- **Emergency mode:** Operations

The plan is tested.

## The "BA" distinction

For BA (Business Associate):
- **BA:** A vendor that touches PHI on your behalf
- **CA:** Covered Entity (hospital, doctor)
- **Subcontractor BA:** A vendor of a BA

Each level needs a BAA.

## The "PHI flow" pattern

For PHI flow:
```
Patient → Covered Entity → [BAA] → Business Associate
                                         → [BAA] → Subcontractor
```

Each arrow needs a BAA.

## The "HIPAA anti-pattern" anti-patterns

### 1. No BAA
- **Issue:** Vendor liability
- **Fix:** Sign BAA

### 2. PHI in logs
- **Issue:** Audit log has PHI
- **Fix:** Redact PHI

### 3. No encryption
- **Issue:** Unencrypted PHI
- **Fix:** Encrypt at rest + in transit

### 4. No access control
- **Issue:** Anyone can read
- **Fix:** RBAC

### 5. No breach plan
- **Issue:** Slow response
- **Fix:** Plan + drill

## Verification
- **Test:** Encryption works
- **Test:** Access control works
- **Test:** Audit log works
- **Live:** Risk assessment
- **Audit:** Annual HIPAA review

## Gotchas
- **The "no BAA" anti-pattern.** Sign a BAA.
- **The "PHI in logs" anti-pattern.** Redact.
- **The "no encryption" anti-pattern.** Encrypt.

## Related
- `compliance/age-gating.md`
- `compliance/gdpr-article-17-erasure.md`
- `compliance/audit-log-mandatory.md`
- `security/encryption-at-rest-detail.md`
- `security/audit-log-security.md`
- HHS HIPAA: https://www.hhs.gov/hipaa/
