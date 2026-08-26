# Contact Picker API Cloudflare Pages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Pages PWA (messaging app, invite flow, address book sync) needs to let users pick one or more contacts from their device's native contact list without the app ever gaining access to the full address book. The data selected (name, phone, email, address) must be forwarded to a Worker for validation, deduplication, or CRM ingestion.

---

## Context

The Contact Picker API (`navigator.contacts.select()`) is available on Chrome for Android 80+ and Safari on iOS 14.5+. It requires HTTPS and a user gesture. Crucially, it is a one-shot picker: the user explicitly chooses what to share, and the app receives only the contacts and properties the user selects. There is no background access to the full address book.

This makes it safe to use in privacy-sensitive flows — your Pages front end never holds a copy of the user's contact list; it only receives what the user explicitly taps.

The Worker leg of this pattern handles:
- Normalizing phone numbers and email addresses.
- Deduplicating against existing records in D1 or KV.
- Returning matched/new status so the UI can show "already invited" vs "new invite".

---

## Feature Detection

```typescript
// src/contacts/support.ts
export interface ContactsCapabilities {
  available: boolean;
  supportedProperties: string[];
}

export async function getContactsCapabilities(): Promise<ContactsCapabilities> {
  if (
    typeof navigator === "undefined" ||
    !("contacts" in navigator) ||
    !("ContactsManager" in window)
  ) {
    return { available: false, supportedProperties: [] };
  }

  const supported = await (navigator.contacts as ContactsManager).getProperties();
  return { available: true, supportedProperties: supported };
}
```

---

## Contact Picker Hook

```typescript
// src/contacts/picker.ts

export interface PickedContact {
  name: string[];
  email: string[];
  tel: string[];
  address: ContactAddress[];
}

export interface PickerOptions {
  multiple?: boolean;
  properties?: Array<"name" | "email" | "tel" | "address" | "icon">;
}

export async function pickContacts(
  options: PickerOptions = {}
): Promise<PickedContact[]> {
  if (!("contacts" in navigator)) {
    throw new Error("Contact Picker API not supported on this browser");
  }

  const {
    multiple = true,
    properties = ["name", "email", "tel"],
  } = options;

  // Validate properties against what the browser supports
  const supported = await (navigator.contacts as ContactsManager).getProperties();
  const validProps = properties.filter((p) => supported.includes(p));

  if (validProps.length === 0) {
    throw new Error("None of the requested contact properties are supported");
  }

  const contacts = await (navigator.contacts as ContactsManager).select(
    validProps,
    { multiple }
  );

  return contacts as PickedContact[];
}
```

---

## Normalizing and Forwarding to Worker

```typescript
// src/contacts/pipeline.ts
import type { PickedContact } from "./picker";

export interface ContactSubmission {
  contacts: NormalizedContact[];
}

export interface NormalizedContact {
  displayName: string | null;
  emails: string[];
  phones: string[];
}

export interface WorkerContactResult {
  results: Array<{
    email: string | null;
    phone: string | null;
    status: "new" | "existing" | "invalid";
    existingUserId: string | null;
  }>;
}

function normalizePhone(raw: string): string {
  // Strip everything except digits and leading +
  return raw.replace(/[^\d+]/g, "");
}

function normalizeEmail(raw: string): string {
  return raw.trim().toLowerCase();
}

export function normalizeContacts(picked: PickedContact[]): NormalizedContact[] {
  return picked.map((c) => ({
    displayName: c.name[0] ?? null,
    emails: c.email.map(normalizeEmail).filter(Boolean),
    phones: c.tel.map(normalizePhone).filter((p) => p.length >= 7),
  }));
}

export async function submitContacts(
  contacts: NormalizedContact[],
  signal?: AbortSignal
): Promise<WorkerContactResult> {
  const res = await fetch("/api/contacts/resolve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ contacts } satisfies ContactSubmission),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: "Server error" }));
    throw new Error(`Contact resolve failed ${res.status}: ${err.message}`);
  }

  return res.json() as Promise<WorkerContactResult>;
}
```

---

## Cloudflare Pages Function — `/api/contacts/resolve`

```typescript
// functions/api/contacts/resolve.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  DB: D1Database;
}

interface NormalizedContact {
  displayName: string | null;
  emails: string[];
  phones: string[];
}

interface ContactSubmission {
  contacts: NormalizedContact[];
}

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  let body: ContactSubmission;
  try {
    body = (await request.json()) as ContactSubmission;
  } catch {
    return Response.json({ message: "Invalid JSON" }, { status: 400 });
  }

  if (!Array.isArray(body.contacts) || body.contacts.length === 0) {
    return Response.json({ message: "contacts array required" }, { status: 422 });
  }

  // Cap at 50 contacts per request to prevent abuse
  const contacts = body.contacts.slice(0, 50);

  const results = await Promise.all(
    contacts.flatMap((contact) => {
      // Resolve each email and phone independently
      const emailChecks = contact.emails.map((email) =>
        resolveIdentifier(env.DB, "email", email)
      );
      const phoneChecks = contact.phones.map((phone) =>
        resolveIdentifier(env.DB, "phone", phone)
      );
      return [...emailChecks, ...phoneChecks];
    })
  );

  return Response.json({ results });
};

async function resolveIdentifier(
  db: D1Database,
  type: "email" | "phone",
  value: string
): Promise<{
  email: string | null;
  phone: string | null;
  status: "new" | "existing" | "invalid";
  existingUserId: string | null;
}> {
  const column = type === "email" ? "email" : "phone";
  const result = await db
    .prepare(`SELECT id FROM users WHERE ${column} = ? LIMIT 1`)
    .bind(value)
    .first<{ id: string }>();

  return {
    email: type === "email" ? value : null,
    phone: type === "phone" ? value : null,
    status: result ? "existing" : "new",
    existingUserId: result?.id ?? null,
  };
}
```

---

## D1 Schema (contacts-related portion)

```sql
CREATE TABLE IF NOT EXISTS users (
  id      TEXT PRIMARY KEY,
  email   TEXT UNIQUE,
  phone   TEXT UNIQUE,
  name    TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_phone ON users (phone);
```

---

## React Component

```typescript
// src/components/ContactPickerButton.tsx
import { useState, useCallback } from "react";
import { getContactsCapabilities, pickContacts } from "../contacts/picker";
import { normalizeContacts, submitContacts } from "../contacts/pipeline";
import type { WorkerContactResult } from "../contacts/pipeline";

export function ContactPickerButton() {
  const [result, setResult] = useState<WorkerContactResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePick = useCallback(async () => {
    setError(null);
    setLoading(true);

    try {
      const capabilities = await getContactsCapabilities();
      if (!capabilities.available) {
        throw new Error("Contact Picker is not available on this device");
      }

      const picked = await pickContacts({ multiple: true, properties: ["name", "email", "tel"] });

      if (picked.length === 0) {
        setLoading(false);
        return; // User dismissed the picker
      }

      const normalized = normalizeContacts(picked);
      const resolved = await submitContacts(normalized);
      setResult(resolved);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  const newCount = result?.results.filter((r) => r.status === "new").length ?? 0;
  const existingCount = result?.results.filter((r) => r.status === "existing").length ?? 0;

  return (
    <div>
      <button onClick={handlePick} disabled={loading} aria-busy={loading}>
        {loading ? "Resolving contacts…" : "Pick Contacts"}
      </button>

      {error && <p role="alert">{error}</p>}

      {result && (
        <p>
          {newCount} new contact{newCount !== 1 ? "s" : ""},{" "}
          {existingCount} already in system
        </p>
      )}
    </div>
  );
}
```

---

## Anti-patterns

- **Requesting the `icon` property by default.** Contact icons are base64-encoded blobs that can exceed 100 KB per contact. Only request `icon` when you genuinely render avatars; strip it from the payload before forwarding to the Worker.
- **Sending raw `PickedContact[]` directly to the Worker.** The browser's `ContactAddress` objects include postal codes, regions, and country codes that may be PII. Normalize to only the fields the application needs before transmission.
- **Assuming `tel` contains E.164-formatted numbers.** The device's contacts store whatever the user typed. You will receive `(555) 867-5309`, `+1 555 867 5309`, and `867-5309` for the same person. Always normalize before comparing.
- **Calling `select()` outside a user gesture.** This throws `SecurityError`. Bind the call to a button `onClick`, not a `useEffect` or timer.
- **Storing full contact records server-side without consent disclosure.** Clearly inform users what is being stored before the pick flow. The API is designed to be ephemeral from the OS perspective; your server side is not.

---

## Gotchas

- On iOS Safari, `navigator.contacts.select()` returns `ContactAddress` objects with all fields optional. Do not assume `city` or `country` is populated.
- The picker UI is entirely native and cannot be styled. Any "match your app theme" expectation from product stakeholders needs to be reset early.
- Chrome on Android will throw `AbortError` if the user dismisses the picker without selecting anyone. This is normal — do not show it as an error to the user.
- `getProperties()` returns an array of strings. The available properties differ by platform; `address` is available on Android but not all iOS builds support all address sub-fields.
- The Contact Picker API is not available in iframes, even same-origin ones. The picker must be called from the top-level browsing context.

---

## Verification

1. Deploy to Pages and open in Chrome on Android or Safari on iOS 14.5+.
2. Tap "Pick Contacts"; verify the OS contact picker opens.
3. Select 2–3 contacts and confirm; verify `picked.length` equals selection count in console.
4. Inspect the normalized payload in the Network tab for the POST to `/api/contacts/resolve`.
5. Verify the Worker returns correct `status: "new" | "existing"` values against D1 data.
6. Test the dismiss case: close the picker without selecting; confirm no error is surfaced.
7. Test on a browser that does not support the API (desktop Chrome) and verify the fallback error message appears.

---

## Related

- `web-nfc-api-workers-scan-pipeline.md`
- `form-validation-zod-workers-endpoint.md`
- `indexeddb-offline-sync-cloudflare-d1-workers.md`
- `user-activation-transient-sticky-gating.md`
- `browser-permissions-api.md`

---

## Sources

- MDN Contact Picker API: https://developer.mozilla.org/en-US/docs/Web/API/Contact_Picker_API
- W3C Contact Picker Specification: https://w3c.github.io/contact-picker/
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
- Cloudflare D1: https://developers.cloudflare.com/d1/
