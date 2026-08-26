# path-traversal-prevention

**Issue:** Unsanitized file path parameters allow attackers to read or write arbitrary files on the server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APIs that serve files based on user-supplied filenames are vulnerable to `../../../etc/passwd` style traversal attacks. This can expose configuration files, secrets, source code, or allow overwriting system files.

## Pattern / Solution
```javascript
import path from 'path';
import fs from 'fs';

const BASE_DIR = '/var/app/uploads';

// INSECURE
app.get('/files/:name', (req, res) => {
  res.sendFile(path.join(BASE_DIR, req.params.name)); // traversal possible
});

// SECURE — resolve and verify path stays within base
app.get('/files/:name', (req, res) => {
  const requested = path.resolve(BASE_DIR, req.params.name);
  if (!requested.startsWith(BASE_DIR + path.sep)) {
    return res.status(403).json({ error: 'Forbidden' });
  }
  res.sendFile(requested);
});
```
```python
# Python equivalent
import os
BASE_DIR = '/var/app/uploads'
def safe_path(filename):
    full = os.path.realpath(os.path.join(BASE_DIR, filename))
    if not full.startswith(BASE_DIR + os.sep):
        raise ValueError('Path traversal detected')
    return full
```

## Gotchas
- `path.join` does NOT prevent traversal — only `path.resolve` + prefix check does.
- Null bytes (`%00`) in filenames can truncate paths in some languages — strip them.
- Symlinks can escape the base directory even after prefix check — use `realpath` to resolve them.
- Windows paths use `\` separators — normalize to OS separator before comparison.

## Related
- `open-redirect-prevention.md`
- `server-side-request-forgery-ssrf.md`
