# browser-clipboard-api

**Issue:** The old document.execCommand copy is deprecated and unreliable
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Copying text to clipboard fails in Safari or requires a textarea hack.

## Pattern / Solution
```ts
// Modern async clipboard API
async function copyToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Fallback for older browsers
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
  }
}

// Read from clipboard (requires permission)
const text = await navigator.clipboard.readText();

// Copy rich content
await navigator.clipboard.write([
  new ClipboardItem({ 'text/html': new Blob(['<b>bold</b>'], { type: 'text/html' }) })
]);
```

## Gotchas
- writeText works without permission prompt; readText requires clipboard-read permission
- Must be triggered by user gesture in many browsers
- HTTPS required

## Related
- `browser-permissions-api.md`
- `browser-share-api.md`
