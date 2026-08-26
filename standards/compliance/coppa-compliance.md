# coppa-compliance

**Issue:** COPPA — children under 13, parental consent
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your app has a "Date of Birth" field. A 12-year-old
signs up. You collect their personal info. You haven't
gotten parental consent. The FTC fines you.

## Root cause
**COPPA applies to under-13 users.** Get parental
consent.

**Source:** FTC COPPA:
https://www.ftc.gov/business-guidance/privacy-security/childrens-privacy

## The "age gate" pattern

For an age gate:
```ts
async function signUp(input: SignupInput, env: Env): Promise<SignupResult> {
  const age = calculateAge(input.dateOfBirth);

  if (age < 13) {
    return { status: 'requires_parental_consent', userId: user.id };
  }

  // Continue
  return { status: 'signed_up', userId: user.id };
}
```

The user is age-gated.

## The "parental consent" pattern

For parental consent:
1. **Collect parent email:** From the child
2. **Send consent email:** To the parent
3. **Parent verifies:** Identity (credit card, ID, etc.)
4. **Consent stored:** Audit trail
5. **Account activated:** For the child

```ts
async function requestParentalConsent(childUserId: string, parentEmail: string, env: Env): Promise<void> {
  const token = crypto.randomUUID();
  await env.DB!.prepare(
    `INSERT INTO consent_requests (id, child_user_id, parent_email, token) VALUES (?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), childUserId, parentEmail, token).run();

  await sendEmail(parentEmail, {
    subject: 'Your child wants to use our service',
    html: `<a href="https://example.com/parent-consent?token=<redacted-secret> your identity</a>`,
  }, env);
}
```

The consent is requested.

## The "verification" pattern

For verification, FTC-approved methods:
- **Credit card:** Small charge
- **Government ID:** Upload + verify
- **Knowledge-based:** Security questions
- **Video conference:** Real-time verification
- **Signed consent form:** Mail/fax

For most apps, **credit card** is the easiest.

## The "data minimization" pattern

For children, collect only what's needed:
- ❌ **Don't collect:** Full name, address, phone
- ✅ **Collect:** Username, password, parent email

```ts
// Limited signup for under-13
interface ChildSignup {
  username: string;
  password: string;
  dateOfBirth: string;
  parentEmail: string;
}
```

The data is minimized.

## The "parental access" pattern

For parental access:
- **Review:** What data is collected
- **Delete:** Request data deletion
- **Stop:** Stop data collection
- **Opt-out:** Opt out of disclosure

```ts
async function getParentalAccess(childUserId: string, env: Env): Promise<ChildDataSummary> {
  return {
    profile: await getUserProfile(childUserId, env),
    activity: await getActivityLog(childUserId, env),
    dataShared: await getDataShared(childUserId, env),
  };
}
```

The parent can review.

## The "deletion" pattern

For deletion, the parent can request:
```ts
async function requestChildDeletion(childUserId: string, parentUserId: string, env: Env): Promise<void> {
  // 1. Verify the parent
  const parent = await getParent(childUserId, env);
  if (parent.id !== parentUserId) {
    throw new Error('Not the parent');
  }

  // 2. Delete the data
  await env.DB!.prepare(`DELETE FROM users WHERE id = ?`).bind(childUserId).run();
  await env.DB!.prepare(`DELETE FROM posts WHERE author_id = ?`).bind(childUserId).run();
  // ... delete all data

  // 3. Audit
  await env.DB!.prepare(
    `INSERT INTO deletions (id, user_id, type) VALUES (?, ?, 'coppa')`
  ).bind(crypto.randomUUID(), childUserId).run();
}
```

The data is deleted.

## The "no behavioral advertising" pattern

For children, no behavioral ads:
- ❌ **No:** Targeted ads
- ❌ **No:** Retargeting
- ✅ **OK:** Contextual ads (e.g. "kids games" section)

```ts
// Don't track for ads
const adConfig = {
  isChild: user.age < 13,
  targeting: !user.age < 13,
};
```

The ads are not behavioral.

## The "safe harbor" pattern

For safe harbor, join a COPPA safe harbor program:
- **iKeepSafe**
- **TRUSTe Children's Privacy Program**
- **kidSAFE**

The safe harbor provides guidance.

## The "audit log" pattern

For audit, log everything:
```sql
CREATE TABLE coppa_audit (
  id TEXT PRIMARY KEY,
  child_user_id TEXT NOT NULL,
  action TEXT NOT NULL,  -- 'signup', 'consent_requested', 'consent_verified', 'data_accessed', 'data_deleted'
  actor TEXT,  -- 'system', 'parent', 'child'
  timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The audit is queryable.

## The "data retention" pattern

For data retention, delete after:
- **Account inactive for 2 years:** Delete
- **Parent requests deletion:** Delete immediately

```ts
async function cleanupInactive(env: Env): Promise<void> {
  const twoYearsAgo = new Date();
  twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);

  await env.DB!.prepare(
    `DELETE FROM users WHERE age < 13 AND last_active_at < ?`
  ).bind(twoYearsAgo.toISOString()).run();
}
```

The data is cleaned up.

## The "COPPA checklist" pattern

For the checklist:
- [ ] Age gate on signup
- [ ] Parental consent for under-13
- [ ] FTC-approved verification
- [ ] Data minimization
- [ ] Parental access
- [ ] Deletion on request
- [ ] No behavioral ads
- [ ] Audit log
- [ ] Data retention policy

## The "COPPA anti-pattern" anti-patterns

### 1. No age gate
- **Issue:** Under-13 without consent
- **Fix:** Age gate

### 2. Self-attested age
- **Issue:** Not enough for COPPA
- **Fix:** Verifiable parental consent

### 3. Behavioral ads for children
- **Issue:** COPPA violation
- **Fix:** Contextual only

### 4. No data minimization
- **Issue:** Over-collection
- **Fix:** Minimize

### 5. No parental access
- **Issue:** Parent can't review
- **Fix:** Parental access

## Verification
- **Test:** Age gate works
- **Test:** Consent flow works
- **Test:** Deletion works
- **Live:** COPPA audit
- **Audit:** Annual COPPA review

## Gotchas
- **The "no age gate" anti-pattern.** Age gate.
- **The "self-attested" anti-pattern.** Verifiable
  consent.
- **The "behavioral ads" anti-pattern.** Contextual.

## Related
- `compliance/age-gating.md`
- `compliance/gdpr-article-17-erasure.md`
- `compliance/ccpa-opt-out.md`
- `compliance/store-region-matrix.md`
- FTC COPPA: https://www.ftc.gov/business-guidance/privacy-security/childrens-privacy
