# browser-file-system-access

**Issue:** Web apps need to read and write files without a server round-trip
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A browser-based text editor needs to open and save files directly to the user's disk.

## Pattern / Solution
```ts
// Open a file
async function openFile(): Promise<string> {
  const [fileHandle] = await window.showOpenFilePicker({
    types: [{ description: 'Text files', accept: { 'text/plain': ['.txt', '.md'] } }],
  });
  const file = await fileHandle.getFile();
  return file.text();
}

// Save a file
async function saveFile(content: string): Promise<void> {
  const fileHandle = await window.showSaveFilePicker({
    suggestedName: 'document.md',
    types: [{ description: 'Markdown', accept: { 'text/markdown': ['.md'] } }],
  });
  const writable = await fileHandle.createWritable();
  await writable.write(content);
  await writable.close();
}
```

## Gotchas
- Only supported in Chromium browsers; Firefox and Safari use the traditional <input type="file"> approach
- File handles can be persisted in IndexedDB and re-used across sessions (with re-permission)
- showDirectoryPicker provides access to an entire directory tree

## Related
- `browser-permissions-api.md`
- `browser-indexeddb-patterns.md`
