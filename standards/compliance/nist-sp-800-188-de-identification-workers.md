# NIST SP 800-188 De-identification of Government Datasets — Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You operate a government-adjacent or federal-contract SaaS and need to publish or share datasets containing PII in a way that satisfies NIST SP 800-188 (De-Identification of Government Datasets). You need Workers-based pipelines that:

- Apply **direct identifier suppression** before export.
- Apply **quasi-identifier generalization** to survive the disclosure-risk threshold.
- Implement **l-diversity** and **t-closeness** checks before releasing aggregate data.
- Log every de-identification action for FISMA audit purposes.

---

## Context

NIST SP 800-188 (2nd draft, 2022) defines de-identification as a process that removes or transforms information so that records cannot be linked to specific individuals. It extends beyond k-anonymity to address:

- **Direct identifiers** (name, SSN, DOB, address, phone, email, biometrics) — must be suppressed or generalized.
- **Quasi-identifiers** (ZIP, age, gender, race) — must be generalized so no equivalence class has fewer than *k* members.
- **Sensitive attributes** — require l-diversity (at least *l* distinct values per equivalence class) and t-closeness (attribute distribution within an equivalence class must be within *t* of the global distribution).
- **Re-identification risk** — requires empirical testing, not assumption.

This standard is cited by FedRAMP, FISMA implementations, and DoD data-sharing agreements.

---

## 1. Direct Identifier Suppression Worker

```typescript
// workers/de-identify-direct.ts
// Removes all NIST SP 800-188 Table 1 direct identifiers before dataset export

const DIRECT_IDENTIFIERS: ReadonlySet<string> = new Set([
  "name", "first_name", "last_name", "full_name",
  "ssn", "social_security_number",
  "date_of_birth", "dob", "birthdate",
  "address", "street_address", "city",
  "phone", "phone_number", "mobile",
  "email", "email_address",
  "drivers_license", "passport_number",
  "account_number", "credit_card",
  "ip_address", "device_id", "mac_address",
  "biometric_hash", "face_image_url",
  "vehicle_vin", "medical_record_number",
]);

export function suppressDirectIdentifiers(
  record: Record<string, unknown>
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    const normalized = key.toLowerCase().replace(/[\s-]/g, "_");
    result[key] = DIRECT_IDENTIFIERS.has(normalized) ? "[SUPPRESSED]" : value;
  }
  return result;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }
    const records = await request.json<Record<string, unknown>[]>();
    const deidentified = records.map(suppressDirectIdentifiers);

    await logDeidentificationAction(
      "direct_suppression",
      records.length,
      env.DB
    );

    return new Response(JSON.stringify(deidentified), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

---

## 2. Quasi-Identifier Generalization (k-Anonymity Enforcer)

```typescript
// lib/k-anonymity.ts
export interface QIGeneralizationConfig {
  age?: { bucketSize: number };        // e.g. 5 → rounds to nearest 5-year band
  zipCode?: { truncateToChars: number }; // e.g. 3 → first 3 digits only
  gender?: { categories: string[] };   // collapse to provided set
}

export function generalizeRecord(
  record: Record<string, unknown>,
  config: QIGeneralizationConfig
): Record<string, unknown> {
  const result = { ...record };

  if (config.age?.bucketSize && typeof result.age === "number") {
    const b = config.age.bucketSize;
    result.age = `${Math.floor(result.age / b) * b}-${Math.floor(result.age / b) * b + b - 1}`;
  }

  if (config.zipCode?.truncateToChars && typeof result.zip_code === "string") {
    result.zip_code = result.zip_code.slice(0, config.zipCode.truncateToChars);
  }

  if (config.gender?.categories && typeof result.gender === "string") {
    result.gender = config.gender.categories.includes(result.gender as string)
      ? result.gender
      : "other";
  }

  return result;
}

// k-anonymity check: every equivalence class must have at least k members
export function checkKAnonymity(
  records: Record<string, unknown>[],
  quasiIdentifiers: string[],
  k: number
): { passes: boolean; minGroupSize: number; violations: string[] } {
  const groups = new Map<string, number>();

  for (const rec of records) {
    const key = quasiIdentifiers.map((qi) => String(rec[qi] ?? "")).join("|");
    groups.set(key, (groups.get(key) ?? 0) + 1);
  }

  const violations: string[] = [];
  let minGroupSize = Infinity;

  for (const [key, count] of groups) {
    if (count < k) violations.push(`${key} (size ${count})`);
    if (count < minGroupSize) minGroupSize = count;
  }

  return { passes: violations.length === 0, minGroupSize, violations };
}
```

---

## 3. l-Diversity Checker

```typescript
// lib/l-diversity.ts
/**
 * For each equivalence class (grouped by quasi-identifiers),
 * verify that there are at least `l` distinct values of the sensitive attribute.
 * NIST SP 800-188 §4.3.3
 */
export function checkLDiversity(
  records: Record<string, unknown>[],
  quasiIdentifiers: string[],
  sensitiveAttribute: string,
  l: number
): { passes: boolean; violations: string[] } {
  const groups = new Map<string, Set<unknown>>();

  for (const rec of records) {
    const key = quasiIdentifiers.map((qi) => String(rec[qi] ?? "")).join("|");
    if (!groups.has(key)) groups.set(key, new Set());
    groups.get(key)!.add(rec[sensitiveAttribute]);
  }

  const violations: string[] = [];
  for (const [key, values] of groups) {
    if (values.size < l) {
      violations.push(`Group [${key}] has only ${values.size} distinct ${sensitiveAttribute} values (need ${l})`);
    }
  }

  return { passes: violations.length === 0, violations };
}
```

---

## 4. D1 De-identification Audit Log

```typescript
// lib/deidentification-log.ts
export async function logDeidentificationAction(
  technique: string,
  recordCount: number,
  db: D1Database,
  params?: Record<string, unknown>
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO deidentification_log
         (technique, record_count, params_json, performed_at, nist_ref)
       VALUES (?, ?, ?, datetime('now'), 'NIST SP 800-188')`
    )
    .bind(technique, recordCount, JSON.stringify(params ?? {}))
    .run();
}

// Schema (run in migration):
// CREATE TABLE IF NOT EXISTS deidentification_log (
//   id             INTEGER PRIMARY KEY AUTOINCREMENT,
//   technique      TEXT NOT NULL,
//   record_count   INTEGER NOT NULL,
//   params_json    TEXT NOT NULL DEFAULT '{}',
//   performed_at   TEXT NOT NULL DEFAULT (datetime('now')),
//   nist_ref       TEXT NOT NULL DEFAULT 'NIST SP 800-188',
//   requester_id   TEXT,
//   dataset_id     TEXT
// );
```

---

## 5. Dataset Export Orchestrator

```typescript
// workers/dataset-export.ts
import { suppressDirectIdentifiers } from "./de-identify-direct";
import { generalizeRecord, checkKAnonymity } from "../lib/k-anonymity";
import { checkLDiversity } from "../lib/l-diversity";
import { logDeidentificationAction } from "../lib/deidentification-log";

const QI_FIELDS = ["age", "zip_code", "gender"];
const K = 5;  // minimum equivalence class size
const L = 3;  // minimum distinct sensitive values

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const { dataset_id, sensitive_attribute } = await request.json<{
      dataset_id: string;
      sensitive_attribute: string;
    }>();

    const { results } = await env.DB.prepare(
      "SELECT * FROM dataset_records WHERE dataset_id = ?"
    )
      .bind(dataset_id)
      .all<Record<string, unknown>>();

    // Step 1: suppress direct identifiers
    const step1 = results.map(suppressDirectIdentifiers);

    // Step 2: generalize quasi-identifiers
    const step2 = step1.map((r) =>
      generalizeRecord(r, { age: { bucketSize: 5 }, zipCode: { truncateToChars: 3 } })
    );

    // Step 3: check k-anonymity
    const kResult = checkKAnonymity(step2, QI_FIELDS, K);
    if (!kResult.passes) {
      await logDeidentificationAction("export_rejected_k_anonymity", step2.length, env.DB, { violations: kResult.violations.slice(0, 5) });
      return new Response(
        JSON.stringify({ error: "k-anonymity violation", minGroupSize: kResult.minGroupSize }),
        { status: 422 }
      );
    }

    // Step 4: check l-diversity
    const lResult = checkLDiversity(step2, QI_FIELDS, sensitive_attribute, L);
    if (!lResult.passes) {
      await logDeidentificationAction("export_rejected_l_diversity", step2.length, env.DB, { violations: lResult.violations.slice(0, 5) });
      return new Response(JSON.stringify({ error: "l-diversity violation" }), { status: 422 });
    }

    await logDeidentificationAction("export_approved", step2.length, env.DB, { dataset_id, k: K, l: L });
    return new Response(JSON.stringify(step2), { headers: { "Content-Type": "application/json" } });
  },
};
```

---

## Anti-patterns

- **Applying de-identification once and assuming permanence**: Auxiliary datasets evolve; a dataset that was k-anonymous when released may be re-identifiable within months.
- **Using k=2 or k=3 in practice**: NIST recommends k≥5 as a baseline; for sensitive health or financial data, k≥10 is standard.
- **Ignoring the sensitive attribute distribution**: k-anonymity alone allows "homogeneity attack" if all members of a group share the same sensitive value — l-diversity is mandatory.
- **Storing de-identified records alongside identified originals without access controls**: Physical or logical separation is required.

---

## Gotchas

- **NIST SP 800-188 is a draft standard**: Federal agencies may cite the draft; treat it as normative for FedRAMP/FISMA contexts while awaiting final publication.
- **ZIP code is a strong quasi-identifier**: Sweeney's 1997 study showed 87% of US residents are uniquely identified by DOB + gender + 5-digit ZIP. Always truncate to 3 digits minimum.
- **Workers CPU limits**: Running l-diversity checks over large datasets in a single Worker invocation may hit the 30s CPU limit. Paginate or offload to a Durable Object.
- **t-closeness is not implemented above**: For datasets with skewed sensitive-attribute distributions, add t-closeness; omitting it is acceptable only for government datasets with confirmed l-diversity.

---

## Verification

```bash
# Check de-identification audit log
wrangler d1 execute DB --command \
  "SELECT technique, record_count, performed_at FROM deidentification_log
   ORDER BY performed_at DESC LIMIT 10;"

# Spot-check no SSNs in exported records
wrangler d1 execute DB --command \
  "SELECT COUNT(*) FROM dataset_records WHERE ssn IS NOT NULL AND ssn != '[SUPPRESSED]';"
```

---

## Related

- `gdpr-pseudonymization-anonymization-workers-d1.md` — GDPR-specific pseudonymization
- `data-minimization-workers-d1-pii-redaction.md` — PII scrubbing at ingest
- `privacy-enhancing-technologies-pets.md` — Differential privacy, synthetic data
- `nist-csf-2-0-implementation-workers.md` — Broader NIST framework alignment
- `fedramp-compliance.md` — FedRAMP context for de-identification obligations

---

## Sources

- NIST SP 800-188 (2nd Public Draft, 2022): https://csrc.nist.gov/publications/detail/sp/800-188/draft
- NIST Privacy Framework: https://www.nist.gov/privacy-framework
- Sweeney (1997) — k-anonymity: https://dataprivacylab.org/dataprivacy/projects/kanonymity/
- Machanavajjhala et al. (2006) — l-diversity: https://doi.org/10.1145/1217299.1217302
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
