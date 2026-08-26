# Local Font Access API Cloudflare Pages Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A design tool, document editor, or brand configurator hosted on Cloudflare Pages needs to enumerate the user's locally installed fonts and let them pick typefaces for rendering. Optionally, the selected font's binary data must be streamed to a Cloudflare Worker — for server-side PDF generation, font subsetting, or cloud storage in R2.

---

## Context

The Local Font Access API (`window.queryLocalFonts()`) is available in Chrome 103+ on desktop (Windows, macOS, Linux). It is not available on Android or iOS. It requires HTTPS, a user gesture for the first call in some implementations, and the `"local-fonts"` permission which the browser prompts for automatically when the API is called.

For a Cloudflare Pages app this means:
1. Feature-detect and gate the UI behind a capability check.
2. Call `queryLocalFonts()` to get a list of `FontData` objects.
3. Render the font list using CSS `@font-face` + `local()` so the user sees a live preview.
4. Optionally call `FontData.blob()` to get the raw font binary, then POST to a Worker that stores it in R2 or forwards to a PDF renderer.

---

## Feature Detection

```typescript
// src/fonts/support.ts
export function isLocalFontAccessSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "queryLocalFonts" in window
  );
}

export async function checkFontPermission(): Promise<PermissionState> {
  if (!isLocalFontAccessSupported()) return "denied";

  try {
    const status = await navigator.permissions.query({
      name: "local-fonts" as PermissionName,
    });
    return status.state;
  } catch {
    // Permissions API may not expose this query on all builds
    return "prompt";
  }
}
```

---

## Querying Local Fonts

```typescript
// src/fonts/query.ts

export interface LocalFont {
  family: string;
  fullName: string;
  postscriptName: string;
  style: string;
}

export async function queryLocalFonts(
  filterFamilies?: string[]
): Promise<LocalFont[]> {
  if (!("queryLocalFonts" in window)) {
    throw new Error("Local Font Access API is not supported in this browser");
  }

  const options: { postscriptNames?: string[] } = {};

  // Optional: filter by PostScript name to reduce the returned set
  // (useful if you only need specific families for a branding tool)
  const results: FontData[] = await (window as Window & {
    queryLocalFonts: (options?: object) => Promise<FontData[]>;
  }).queryLocalFonts(options);

  const fonts: LocalFont[] = results.map((f) => ({
    family: f.family,
    fullName: f.fullName,
    postscriptName: f.postscriptName,
    style: f.style,
  }));

  if (filterFamilies && filterFamilies.length > 0) {
    const filterSet = new Set(filterFamilies.map((f) => f.toLowerCase()));
    return fonts.filter((f) => filterSet.has(f.family.toLowerCase()));
  }

  return fonts;
}

export function groupByFamily(fonts: LocalFont[]): Map<string, LocalFont[]> {
  const map = new Map<string, LocalFont[]>();
  for (const font of fonts) {
    const group = map.get(font.family) ?? [];
    group.push(font);
    map.set(font.family, group);
  }
  return map;
}
```

---

## CSS Preview with `local()` References

```typescript
// src/fonts/preview.ts

/**
 * Injects a <style> block that makes local font families available
 * to CSS via @font-face local() references. The browser resolves
 * them against the system font cache — no font data is transmitted.
 */
export function injectLocalFontPreviewStyles(families: string[]): () => void {
  const id = "local-font-preview-styles";
  document.getElementById(id)?.remove();

  const rules = families
    .map(
      (family) => `
@font-face {
  font-family: ${JSON.stringify(family)};
  src: local(${JSON.stringify(family)});
}`
    )
    .join("\n");

  const style = document.createElement("style");
  style.id = id;
  style.textContent = rules;
  document.head.appendChild(style);

  return () => style.remove();
}
```

---

## Uploading Font Binary to R2 via Worker

```typescript
// src/fonts/upload.ts

export interface FontUploadResult {
  r2Key: string;
  sizeBytes: number;
  uploadedAt: string;
}

export async function uploadFontToR2(
  fontData: FontData,
  signal?: AbortSignal
): Promise<FontUploadResult> {
  // FontData.blob() yields the raw font file (TTF, OTF, WOFF2, etc.)
  const blob = await fontData.blob();

  const res = await fetch("/api/fonts/upload", {
    method: "POST",
    headers: {
      "Content-Type": blob.type || "application/octet-stream",
      "X-Font-PostScript-Name": encodeURIComponent(fontData.postscriptName),
      "X-Font-Family": encodeURIComponent(fontData.family),
    },
    body: blob,
    signal,
    // Disable response body buffering for large fonts
    duplex: "half" as RequestInit["duplex"],
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: "Upload failed" }));
    throw new Error(`Font upload error ${res.status}: ${err.message}`);
  }

  return res.json() as Promise<FontUploadResult>;
}
```

---

## Cloudflare Pages Function — `/api/fonts/upload`

```typescript
// functions/api/fonts/upload.ts
import type { PagesFunction } from "@cloudflare/workers-types";

interface Env {
  FONT_BUCKET: R2Bucket;
}

const MAX_FONT_SIZE = 10 * 1024 * 1024; // 10 MB

export const onRequestPost: PagesFunction<Env> = async ({ request, env }) => {
  const contentLength = parseInt(request.headers.get("Content-Length") ?? "0", 10);
  if (contentLength > MAX_FONT_SIZE) {
    return Response.json({ message: "Font file too large (max 10 MB)" }, { status: 413 });
  }

  const rawPostscript = request.headers.get("X-Font-PostScript-Name");
  const rawFamily = request.headers.get("X-Font-Family");

  if (!rawPostscript) {
    return Response.json({ message: "Missing X-Font-PostScript-Name header" }, { status: 400 });
  }

  const postscriptName = decodeURIComponent(rawPostscript);
  const family = rawFamily ? decodeURIComponent(rawFamily) : postscriptName;

  // Sanitize the PostScript name for use as an R2 key
  const safeKey = `fonts/${postscriptName.replace(/[^a-zA-Z0-9_\-\.]/g, "_")}.bin`;

  const body = request.body;
  if (!body) {
    return Response.json({ message: "Empty request body" }, { status: 400 });
  }

  const contentType = request.headers.get("Content-Type") ?? "application/octet-stream";

  await env.FONT_BUCKET.put(safeKey, body, {
    httpMetadata: { contentType },
    customMetadata: {
      family,
      postscriptName,
      uploadedAt: new Date().toISOString(),
    },
  });

  const object = await env.FONT_BUCKET.head(safeKey);

  return Response.json({
    r2Key: safeKey,
    sizeBytes: object?.size ?? 0,
    uploadedAt: object?.customMetadata?.uploadedAt ?? new Date().toISOString(),
  }, { status: 201 });
};
```

---

## React Hook — Font Picker

```typescript
// src/hooks/useLocalFonts.ts
import { useState, useEffect, useCallback } from "react";
import { isLocalFontAccessSupported, checkFontPermission } from "../fonts/support";
import { queryLocalFonts, groupByFamily, type LocalFont } from "../fonts/query";
import { injectLocalFontPreviewStyles } from "../fonts/preview";

export function useLocalFonts() {
  const [supported] = useState(isLocalFontAccessSupported);
  const [permission, setPermission] = useState<PermissionState>("prompt");
  const [fonts, setFonts] = useState<LocalFont[]>([]);
  const [grouped, setGrouped] = useState<Map<string, LocalFont[]>>(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkFontPermission().then(setPermission);
  }, []);

  const loadFonts = useCallback(async () => {
    if (!supported) return;
    setLoading(true);
    setError(null);

    try {
      const result = await queryLocalFonts();
      setFonts(result);
      const byFamily = groupByFamily(result);
      setGrouped(byFamily);

      // Inject preview CSS for all families
      const families = Array.from(byFamily.keys());
      injectLocalFontPreviewStyles(families);

      const perm = await checkFontPermission();
      setPermission(perm);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [supported]);

  return { supported, permission, fonts, grouped, loading, error, loadFonts };
}
```

---

## Anti-patterns

- **Calling `queryLocalFonts()` in a `useEffect` on mount without a gate.** The API prompts for permission on first call. Triggering the permission dialog before the user understands why they're seeing it leads to denials. Always trigger from an explicit user action.
- **Calling `FontData.blob()` for the entire font list.** Loading every font's binary can consume gigabytes of memory on systems with large font libraries. Only call `.blob()` on fonts the user explicitly selects for upload or processing.
- **Using the full font family name in an R2 key without sanitization.** Family names like `"Helvetica Neue (PostScript)"` contain characters illegal in R2 object keys. Always sanitize.
- **Rendering 500+ `@font-face` rules in a single `<style>` block.** This can measurably slow layout recalculation. Group and lazy-inject only visible fonts, or virtualize the font list.
- **Treating PostScript name as a stable identifier across systems.** PostScript names can vary between font versions. Use them for R2 keys but not as a cross-system primary key in a database.

---

## Gotchas

- `queryLocalFonts()` returns duplicate families if the system has multiple weights/styles installed. Use `groupByFamily()` to deduplicate before rendering a picker.
- Font blobs from `FontData.blob()` may be TTF, OTF, or WOFF2 depending on what is installed. The `blob.type` MIME type is usually set correctly but may be empty on older Chrome builds — default to `application/octet-stream`.
- The Local Font Access API is not available in Service Workers or Web Workers — it is main-thread only.
- On macOS, fonts installed in `/System/Library/Fonts/` are returned by the API, but Apple system fonts have licensing restrictions on redistribution. Do not allow users to upload system fonts to your R2 bucket without a clear redistribution-rights check.
- Permission can be revoked by the user in `chrome://settings/content/localFonts`. If the permission state changes, `queryLocalFonts()` will throw `NotAllowedError`. Handle this and prompt re-authorization.

---

## Verification

1. Open the Pages site in Chrome 103+ on desktop.
2. Click "Load Fonts" and confirm the permission prompt appears.
3. Grant permission; verify `fonts.length` reflects the number of installed fonts.
4. Select a single font and click "Upload"; verify the POST to `/api/fonts/upload` in Network tab.
5. In the Cloudflare dashboard, navigate to R2 → `FONT_BUCKET` and confirm the object exists at `fonts/{postscriptName}.bin`.
6. Check `object.customMetadata` for `family` and `uploadedAt` fields.
7. Deny permission in a second browser profile and verify the fallback message renders correctly.

---

## Related

- `font-loading-optimization.md`
- `font-loading-cloudflare-pages-mobile.md`
- `variable-fonts-loading-strategy.md`
- `cloudflare-r2-presigned-upload-frontend.md`
- `browser-permissions-api.md`

---

## Sources

- MDN Local Font Access API: https://developer.mozilla.org/en-US/docs/Web/API/Local_Font_Access_API
- W3C CSS Font Loading spec: https://drafts.csswg.org/css-font-loading/
- Chrome Local Font Access explainer: https://github.com/WICG/local-font-access
- Cloudflare R2: https://developers.cloudflare.com/r2/
- Cloudflare Pages Functions: https://developers.cloudflare.com/pages/functions/
