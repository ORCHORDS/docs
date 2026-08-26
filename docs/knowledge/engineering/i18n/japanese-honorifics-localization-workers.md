# Japanese Honorifics Localization on Cloudflare Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A SaaS product serving Japanese users must address customers with the correct honorific suffix (`様`, `さん`, `君`, `先生`, etc.) in transactional emails and UI copy generated at the edge. Choosing the wrong register embarrasses the company and signals cultural unfamiliarity. The honorific level depends on the relationship context: B2B invoices require `様` while community dashboards may use `さん`.

## Context

Japanese has multiple politeness registers (*keigo*): *sonkeigo* (respectful), *kenjōgo* (humble), and *teineigo* (polite). For product copy the most critical decision is choosing the correct name suffix. Unlike Western titles, Japanese honorifics are appended to the family name (or full name in some informal contexts) and the correct choice is driven by the relationship type stored in your user record, not by locale alone. Cloudflare Workers can read this relationship context from a D1 database or a KV store and assemble the correctly addressed string before the response is sent, without a round-trip to an origin server.

## Honorific Lookup at the Edge

```typescript
// src/honorifics.ts
export type Register =
  | "formal"    // 様 — B2B / official correspondence
  | "polite"    // さん — general / consumer
  | "familiar"  // 君 — colleague / peer (male-coded, use carefully)
  | "academic"; // 先生 — teacher, doctor, lawyer

const SUFFIX_MAP: Record<Register, string> = {
  formal:   "様",
  polite:   "さん",
  familiar: "君",
  academic: "先生",
};

export interface NameRecord {
  familyName: string;
  givenName: string;
  register: Register;
}

/**
 * Returns the addressed name in Japanese convention:
 * family-name first, suffix appended, no space.
 * Example: { familyName: "田中", givenName: "花子", register: "formal" }
 *          → "田中様"
 */
export function formatJapaneseName(record: NameRecord): string {
  const suffix = SUFFIX_MAP[record.register];
  // Japanese convention: family name + honorific (given name omitted in formal contexts)
  return `${record.familyName}${suffix}`;
}

/**
 * For informal/community contexts the full name may be used:
 * "田中花子さん"
 */
export function formatJapaneseFullName(record: NameRecord): string {
  const suffix = SUFFIX_MAP[record.register];
  return `${record.familyName}${record.givenName}${suffix}`;
}
```

## D1 Register Lookup and Edge Assembly

```typescript
// src/worker.ts
import { formatJapaneseName, formatJapaneseFullName, NameRecord } from "./honorifics";

interface Env {
  DB: D1Database;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = url.searchParams.get("userId");

    if (!userId) {
      return new Response("Missing userId", { status: 400 });
    }

    // Fetch user record including the relationship register
    const row = await env.DB
      .prepare(
        `SELECT family_name, given_name, relationship_register
         FROM users
         WHERE id = ?1 LIMIT 1`
      )
      .bind(userId)
      .first<{ family_name: string; given_name: string; relationship_register: string }>();

    if (!row) {
      return new Response("User not found", { status: 404 });
    }

    const record: NameRecord = {
      familyName: row.family_name,
      givenName:  row.given_name,
      register:   (row.relationship_register as NameRecord["register"]) ?? "polite",
    };

    // Build greeting for a transactional email subject line
    const salutation = formatJapaneseName(record);
    const body = JSON.stringify({
      salutation,           // e.g. "田中様"
      fullName: formatJapaneseFullName(record), // e.g. "田中花子様"
    });

    return new Response(body, {
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  },
};
```

## Polite-Form Verb Conjugation for System Messages

```typescript
// src/teineigo.ts

/**
 * Japanese UI strings often need to match the politeness register.
 * Store two variants per message key and select at render time.
 */
type MessageKey =
  | "save_success"
  | "delete_confirm"
  | "welcome";

const MESSAGES: Record<MessageKey, Record<"formal" | "polite", string>> = {
  save_success: {
    formal: "保存が完了いたしました。",   // kenjōgo — humble form
    polite: "保存しました。",             // teineigo — plain polite
  },
  delete_confirm: {
    formal: "削除してもよろしいでしょうか？",
    polite: "削除しますか？",
  },
  welcome: {
    formal: "ご利用いただきありがとうございます。",
    polite: "ようこそ！",
  },
};

export function getMessage(
  key: MessageKey,
  register: "formal" | "polite"
): string {
  return MESSAGES[key][register];
}

// Usage in a Worker response:
// const msg = getMessage("save_success", userRegister);
// → "保存が完了いたしました。" for B2B users
```

## Anti-patterns

- Hardcoding `さん` for every Japanese user — formal business correspondence requires `様` and academic contexts require `先生`.
- Appending the honorific to the given name instead of the family name in formal contexts (`花子様` vs `田中様`).
- Translating honorifics directly as "Mr./Ms." in English fallback strings — they carry different nuance and should be omitted in non-Japanese locales.

## Gotchas

- `先生` is gender-neutral and profession-neutral in modern usage; it applies to doctors, lawyers, and professors equally — do not restrict it to teachers.
- Avoid `君` in B2C products targeting mixed or unknown audiences; it carries a male-coded, superior-to-inferior connotation that can offend female users.

## Verification

```bash
# Seed a D1 test record and verify the Worker response
wrangler d1 execute DB --local \
  --command "INSERT INTO users (id, family_name, given_name, relationship_register) \
             VALUES ('u1', '田中', '花子', 'formal')"

curl "http://localhost:8787?userId=u1" | jq .
# Expected: { "salutation": "田中様", "fullName": "田中花子様" }

wrangler d1 execute DB --local \
  --command "UPDATE users SET relationship_register = 'polite' WHERE id = 'u1'"

curl "http://localhost:8787?userId=u1" | jq .
# Expected: { "salutation": "田中さん", "fullName": "田中花子さん" }
```

## Related

- `i18n/personal-name-formatting-2026.md`
- `i18n/icu-messageformat-2026.md`
- `i18n/d1-schema-locale-preferences-content-translations-2026.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.bunka.go.jp/seisaku/bunkashingikai/kokugo/hokoku/pdf/keigo_tebiki.pdf
- https://unicode.org/reports/tr35/tr35-general.html#Name_Order_Locale
