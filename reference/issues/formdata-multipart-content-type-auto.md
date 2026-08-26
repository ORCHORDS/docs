# formdata-multipart-content-type-auto

**Issue:** Manually setting `Content-Type: multipart/form-data` on a `FormData` fetch breaks the request because the boundary parameter is missing
**Date:** 2026-08-11
**Status:** documented

## Symptom
The server receives the multipart body but cannot parse it. Error: "Missing boundary in multipart/form-data" or the fields are empty. The request was sent with `fetch` and `Content-Type` was set manually.

## Root cause
Multipart requests require a `boundary` parameter in the `Content-Type` header: `Content-Type: multipart/form-data; boundary=----WebKitFormBoundary...`. The browser/runtime generates a unique boundary and appends it automatically — but only if you do NOT manually set `Content-Type`. Setting it manually overrides the auto-generated header without the boundary.

## Fix
```ts
const form = new FormData();
form.append('file', blob, 'upload.png');

// Wrong — removes the boundary
const response = await fetch('/upload', {
  method: 'POST',
  headers: { 'Content-Type': 'multipart/form-data' }, // breaks it
  body: form,
});

// Correct — omit Content-Type, let the runtime set it
const response = await fetch('/upload', {
  method: 'POST',
  body: form,
});
```

## Detection
```
grep -rn "multipart/form-data" src/ --include="*.ts"
```

## Related
- `fetch-no-throw-on-4xx.md`
- `url-searchparams-encoding.md`
