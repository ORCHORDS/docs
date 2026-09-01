# FileSystemObserver Watching Directory Changes

## Scope

Using the `FileSystemObserver` API to observe a `FileSystemFileHandle` or `FileSystemDirectoryHandle` obtained through the File System Access API, receiving change records when files or directories are created, modified, moved, or removed. Covers the observer lifecycle (`observe`, callback records, `disconnect`), the record shape (`changedHandle`, `type`, `relativePathComponents`), recursion semantics, and coordination with the Origin Private File System. Excludes the picker APIs (`showOpenFilePicker`/`showDirectoryPicker`) except as handle sources, and excludes the legacy `FileList`-based drag-and-drop path.

## Workflow or implementation guidance

Before `FileSystemObserver`, watching a picked directory meant polling: re-reading `entries()` on a timer, diffing names and last-modified stamps, and burning the read permission on every pass. The observer pushes changes instead, with the browser computing deltas against a per-observer snapshot.

The basic unit is one observer per watched tree:

```js
const dirHandle = await showDirectoryPicker({ mode: 'read' });
const observer = new FileSystemObserver(records => {
  for (const record of records) {
    console.log(record.type, record.relativePathComponents, record.changedHandle);
  }
});
await observer.observe(dirHandle, { recursive: true });
```

Each callback invocation delivers a batch of records. `record.type` is one of `appeared`, `disappeared`, `modified`, `moved`, `errored`, or `unknown`. `record.relativePathComponents` is the path of the affected entry relative to the observed root as an array of names — `['src', 'index.ts']` for `src/index.ts` under the observed directory. `record.changedHandle` is the post-event handle (for `disappeared` there is no handle; for `moved`, `changedHandle` is the destination and `previousRelativePathComponents` carries where it came from).

Handling is event-sourcing-shaped: maintain a materialized view (a file tree in memory or IndexedDB), apply each record as it arrives, and treat the callback as your single writer. Because multiple records arrive per batch, apply them in order — a `disappeared` for a path followed by an `appeared` at the same path is the observable signature of an atomic replace (save-via-temp-and-rename), which editors do constantly.

The observation must be explicitly disconnected when the watching UI goes away (`observer.disconnect()`), and every observer is tied to the document: a page reload drops all observations. The durable pattern is to persist the directory handle itself (it is structured-cloneable into IndexedDB) and re-observe after regaining permission:

```js
// after reload: read handle from IndexedDB, then
const perm = await dirHandle.queryPermission({ mode: 'read' });
if (perm === 'granted') {
  await newObserver.observe(dirHandle, { recursive: true });
} else {
  // requestPermission needs a user gesture — surface a "resume watching" button
}
```

Recursion is opt-in per `observe()` call. With `recursive: false` on a directory, only direct children produce records; nested changes are invisible. Nested observers are an alternative but each adds snapshot memory and callback overhead — prefer one recursive observer over N shallow ones.

The error record (`type: 'errored'`) is the signal that the observation stream broke: the watched directory was unmounted, the underlying permission was revoked, or an implementation limit was hit. It is terminal for that observation — stop applying deltas, show a re-sync affordance, and re-observe from a fresh full scan, because the observer's snapshot and reality have diverged beyond the delta protocol.

On OPFS: same observer, same records, handles from `navigator.storage.getDirectory()`. This is the cheap wire-up for a local-first editor — watch the OPFS root, mirror changes to a sync queue — with no permission prompt because OPFS is same-origin by construction.

## Controls

- One recursive observer per watched root; batch-apply records inside the callback in delivery order.
- Persist handles in IndexedDB and re-observe on load, gated on `queryPermission` — never call `requestPermission` outside a gesture.
- Treat `errored` records as fatal for the observation: halt delta application and require a full rescan before resuming.
- Debounce downstream work (re-index, re-render) by path: editors emit `modified` bursts per keystroke-save; a 100–300 ms path-keyed debounce collapses them.
- `observer.disconnect()` in teardown paths (component unmount, tab `pagehide`) to release snapshot memory deterministically.

## Validation evidence

- Scripted change battery against a real picked directory: create file, create nested dir, modify (write bytes), rename within root, move across subdirectories, delete, and rename the observed root itself — assert the exact record types and `relativePathComponents` for each.
- Atomic-replace test: write `tmp` then `rename` over an existing file; assert the callback yields `disappeared` + `appeared` (or `modified` depending on engine) and that the materialized view converges to one entry.
- Reload/resume test: persist handle, reload, verify observation resumes only after permission is re-granted, and that changes made while unobserved are detected by the mandatory full rescan.
- Permission-revocation test via site settings: assert the `errored` record (or observer exception) surfaces in UI rather than a silently stalled tree.

## Failure modes and correction

- No records ever arrive: `recursive: false` was left default and the changes are nested — set `recursive: true`, or observe the specific subdirectory.
- Records stop after a while on a picked directory: the user revoked the grant or the volume slept; the `errored` record is the trail — handle it explicitly instead of assuming silence means no changes.
- Stale view after reload: observations do not survive navigation; the resume path (persisted handle + re-observe + rescan) is mandatory, not optional.
- `observe()` rejects with `InvalidStateError`: the handle was invalidated (file replaced on disk, directory deleted) — re-acquire via the picker instead of retrying the dead handle.
- Memory growth with long-lived observers on huge trees: each observer maintains snapshot state proportional to the tree; scope observations to the deepest useful subtree rather than a filesystem root.
- Duplicated work because both a poller and an observer run: delete the poller; the observer's delta contract replaces diffing, and the poller's reads can mask a broken observation by papering over missing records.

## Limitations

- Chromium-only shipping surface as of this writing; feature-detect `('FileSystemObserver' in window)` and keep polling as the fallback for other engines.
- Change payloads are metadata-level: `modified` says the file changed, not which bytes — recompute file content or hashes yourself when the delta content matters.
- No cross-origin watching: handles are same-origin; watched external directories depend on the user grant and are still surfaced through the picker's permission model.
- Record delivery timing is coalesced by the implementation; do not build ordering-sensitive logic on intra-batch timestamps.
- The picker-derived grant can require re-approval across sessions; budget UX for the "resume watching" gesture.

## Canonical sources

- WHATWG, File System Standard, `FileSystemObserver`: https://fs.spec.whatwg.org/#api-filesystemobserver
- WHATWG, File System Access developer documentation: https://developer.mozilla.org/en-US/docs/Web/API/File_System_API
- MDN, `FileSystemObserver`: https://developer.mozilla.org/en-US/docs/Web/API/FileSystemObserver
- WHATWG, File System Standard (OPFS): https://fs.spec.whatwg.org/#origin-private-file-system
