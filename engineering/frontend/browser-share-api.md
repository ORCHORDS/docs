# browser-share-api

**Issue:** Sharing content requires opening separate social media windows
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Users on mobile want to share a link to their native share sheet but the app only offers share buttons for specific platforms.

## Pattern / Solution
```ts
async function share(data: { title?: string; text?: string; url?: string }) {
  if (!navigator.canShare || !navigator.canShare(data)) {
    // Fallback: copy to clipboard
    await navigator.clipboard.writeText(data.url ?? '');
    showToast('Link copied');
    return;
  }
  try {
    await navigator.share(data);
  } catch (err) {
    if ((err as Error).name !== 'AbortError') throw err;
  }
}

// Share a file
const file = new File([blob], 'image.png', { type: 'image/png' });
await navigator.share({ files: [file], title: 'Photo' });
```

## Gotchas
- navigator.share must be triggered by a user gesture
- AbortError is thrown when the user dismisses the share sheet; do not treat as an error
- File sharing (Web Share Level 2) has lower browser support than URL sharing

## Related
- `browser-clipboard-api.md`
- `pwa-manifest-config.md`
