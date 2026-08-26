# Washington My Health My Data Act: Compliance in Workers + D1

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You process health-related data of Washington State residents — including location data near healthcare facilities, fitness metrics, reproductive health, or purchases of health-related products — and must comply with the Washington My Health My Data Act (WMHMDA, RCW 70.372), which carries a private right of action enforceable by any WA resident.

## Context
The WMHMDA (SB 1155, signed 27 April 2023; large-business effective 31 March 2024, all businesses 30 June 2024) defines "consumer health data" far more broadly than HIPAA: it covers any personal information that can reasonably identify a consumer's past, present, or future physical or mental health status, including location signals that could infer proximity to a reproductive health clinic, purchases of over-the-counter medications, and fitness wearable data. The law prohibits geofencing around healthcare facilities, requires affirmative authorisation before sharing or selling health data, and mandates a standalone Consumer Health Data Privacy Policy separate from the general privacy notice. Workers enforce consent at the edge; D1 stores health-data authorisations and the geofence audit log.

## Consumer Health Data Privacy Policy Endpoint

WMHMDA §10 requires a separate, publicly available Consumer Health Data Privacy Policy describing what health data is collected, with whom it is shared, and how subjects can exercise their rights.

```typescript
// src/wmhmda-policy.ts
export function serveHealthDataPolicy(): Response {
  const policy = {
    policy_type: 'Consumer Health Data Privacy Policy',
    statute: 'Washington My Health My Data Act, RCW 70.372',
    effective_date: '2024-03-31',
    last_updated: '2026-08-23',
    categories_collected: [
      'Body measurements and vital signs from connected devices',
      'Reproductive and sexual health indicators',
      'Mental health status derived from app interaction patterns',
      'Precise geolocation when near a healthcare facility',
      'Purchases of prescription and over-the-counter health products',
    ],
    sharing: {
      sold: false,
      shared_with_third_parties: false,
      exceptions: ['Service providers acting on our instructions under contract'],
    },
    subject_rights: {
      access: 'Email privacy@example.com — response within 45 days',
      deletion: 'Email privacy@example.com — response within 45 days',
      withdraw_authorisation: 'Settings → Health Data → Revoke',
    },
    geofencing: 'We do not deploy geofences around healthcare facilities. RCW 70.372.060.',
    contact: 'privacy@example.com',
  };
  return Response.json(policy, {
    headers: { 'Cache-Control': 'public, max-age=86400' },
  });
}
```

## Affirmative Authorisation Gate

WMHMDA §§20-30 require separate, voluntary, affirmative authorisation before collecting, using, or sharing consumer health data. Bundled consent inside a general terms-of-service acceptance does not satisfy this requirement.

```typescript
// src/wmhmda-consent.ts
interface Env {
  DB: D1Database;
}

type HealthDataCategory =
  | 'location_near_healthcare'
  | 'reproductive_health'
  | 'mental_health'
  | 'biometric_health'
  | 'fitness_metrics'
  | 'otc_purchases'
  | 'prescription_history';

interface HealthAuthorisation {
  user_id: string;
  categories: HealthDataCategory[];
  purpose: string;
  sharing_with: string[]; // empty array = first-party only
  authorised_at: string;
  ip_address: string;
  auth_method: 'explicit_checkbox' | 'signed_form';
}

export async function recordHealthAuthorisation(
  env: Env,
  auth: HealthAuthorisation
): Promise<void> {
  for (const category of auth.categories) {
    await env.DB.prepare(`
      INSERT INTO wmhmda_authorisations
        (user_id, category, purpose, sharing_with_json,
         authorised_at, ip_address, auth_method)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).bind(
      auth.user_id,
      category,
      auth.purpose,
      JSON.stringify(auth.sharing_with),
      auth.authorised_at,
      auth.ip_address,
      auth.auth_method
    ).run();
  }
}

export async function requireHealthAuthorisation(
  env: Env,
  userId: string,
  category: HealthDataCategory
): Promise<Response | null> {
  const auth = await env.DB.prepare(`
    SELECT id FROM wmhmda_authorisations
    WHERE user_id = ? AND category = ? AND revoked_at IS NULL
    LIMIT 1
  `).bind(userId, category).first();

  if (!auth) {
    return Response.json(
      {
        error: 'WMHMDA_AUTHORISATION_REQUIRED',
        message:
          'Affirmative authorisation required under RCW 70.372.020 before collecting this health data category.',
        authorisation_url: '/health-data-consent',
        category,
      },
      { status: 451 }
    );
  }
  return null;
}

export async function revokeHealthAuthorisation(
  env: Env,
  userId: string,
  category: HealthDataCategory
): Promise<void> {
  await env.DB.prepare(`
    UPDATE wmhmda_authorisations
    SET revoked_at = ?
    WHERE user_id = ? AND category = ? AND revoked_at IS NULL
  `).bind(new Date().toISOString(), userId, category).run();
}
```

## Geofence Prohibition Enforcement

WMHMDA §60 prohibits deploying a geofence around any healthcare facility to identify, track, or send notifications to consumers. Enforce this at the Workers edge by inspecting any geofence configuration before it is persisted.

```typescript
// src/wmhmda-geofence.ts

// Healthcare facility types as classified by WMHMDA §10(4)
const PROHIBITED_GEOFENCE_TAGS = new Set([
  'hospital',
  'clinic',
  'reproductive_health',
  'abortion_provider',
  'mental_health_facility',
  'substance_abuse_treatment',
  'urgent_care',
  'pharmacy',
  'laboratory',
]);

interface GeofenceConfig {
  name: string;
  lat: number;
  lng: number;
  radius_meters: number;
  tags: string[];
}

export function assertWmhmdaGeofenceLegal(config: GeofenceConfig): void {
  const blocked = config.tags.filter((t) => PROHIBITED_GEOFENCE_TAGS.has(t));
  if (blocked.length > 0) {
    throw new Error(
      `WMHMDA §60 violation: geofence "${config.name}" targets ` +
        `prohibited healthcare facility types: ${blocked.join(', ')}. ` +
        'This is unlawful under RCW 70.372.060.'
    );
  }
}

export async function logGeofenceAttempt(
  env: Env,
  config: GeofenceConfig,
  blocked: boolean,
  reason: string
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO wmhmda_geofence_audit
      (geofence_name, lat, lng, radius_meters, tags_json, blocked, reason, attempted_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    config.name,
    config.lat,
    config.lng,
    config.radius_meters,
    JSON.stringify(config.tags),
    blocked ? 1 : 0,
    reason,
    new Date().toISOString()
  ).run();
}
```

## Anti-patterns
- Collecting location data near a healthcare facility without WMHMDA authorisation — §§20, 60
- Bundling health data consent into a general "I agree to the Terms" checkbox — does not meet affirmative authorisation standard
- Sharing consumer health data with data brokers or ad networks — prohibited without authorisation
- Omitting a standalone Consumer Health Data Privacy Policy — §10 requires it to be separate from the general policy
- Deploying conversion or remarketing pixels that resolve location near clinics — constitutes prohibited geofencing
- Selling consumer health data under any circumstances without explicit per-sale authorisation

## Gotchas
- WMHMDA's definition of "consumer health data" is far broader than HIPAA — it covers app usage patterns, location inferences, and OTC purchases
- Private right of action: any Washington resident can sue; no need to wait for the Attorney General
- The AG can also enforce via Washington Consumer Protection Act, adding treble damages exposure
- A "small business" exemption exists for entities processing data of fewer than 100,000 consumers per year — but the geofence prohibition applies to all entities regardless of size
- Location data can become consumer health data when it reveals visits to a pharmacy, clinic, or mental health provider
- The right to deletion covers all consumer health data collected — not just data collected after the effective date

## Verification

```sql
-- Consumers whose health data was collected without authorisation
SELECT DISTINCT u.id, u.email, hd.category, hd.collected_at
FROM health_data hd
JOIN users u ON hd.user_id = u.id
LEFT JOIN wmhmda_authorisations wa
  ON hd.user_id = wa.user_id
  AND hd.category = wa.category
  AND wa.revoked_at IS NULL
WHERE wa.id IS NULL
  AND u.state = 'WA';

-- Blocked geofence attempts
SELECT geofence_name, tags_json, reason, attempted_at
FROM wmhmda_geofence_audit
WHERE blocked = 1
ORDER BY attempted_at DESC
LIMIT 50;

-- Pending deletion requests (must complete within 45 days)
SELECT id, user_id, received_at,
       DATE(received_at, '+45 days') AS deadline, status
FROM wmhmda_deletion_requests
WHERE status = 'pending'
ORDER BY deadline ASC;
```

## Related
- `hipaa-technical-safeguards-web-api.md`
- `ccpa-cpra-consumer-rights-operations.md`
- `gdpr-right-to-erasure-d1-r2-pipeline.md`
- `location-data-privacy-workers.md`
- `data-retention-automated-deletion-workers.md`
- `age-appropriate-design-codes-children-privacy.md`

## Sources
- https://app.leg.wa.gov/RCW/default.aspx?cite=70.372
- https://lawfilesext.leg.wa.gov/biennium/2023-24/Pdf/Bills/Session%20Laws/Senate/1155-S.SL.pdf
- https://oag.wa.gov/consumer-protection/privacy/my-health-my-data
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/
