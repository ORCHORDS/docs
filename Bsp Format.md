> Auto-generated from `Bsp Format.md` in the docs repo.

> Auto-generated from `Bsp Format.md` in the docs repo.

> Auto-generated from `Bsp Format.md` in the docs repo.

> Auto-generated from `Bsp Format.md` in the docs repo.

> Auto-generated from `Bsp Format.md` in the docs repo.

> Auto-generated from `docs/architecture/BSP_FORMAT.md` in the docs repo.

---
title: "`.bsp` - Beetle Studio Project File Format (v0.1)"
version: "1.0.0"
last-updated: "2026-06-21"
status: "review"
---

# `.bsp` - Beetle Studio Project File Format (v0.1)

> **Status:** Draft v0.1. Subject to change before v1.0.

A `.bsp` (Beetle Studio Project) file is a UTF-8 JSON document describing a single
editing project. It is lossless: opening and saving a project round-trips every
field the editor knows about.

## Top-level shape

```json
{
  "format":    "bsp",
  "version":   "0.1",
  "generator": "BeetleStudio/1.0.0",
  "createdAt": "2026-06-20T10:30:00Z",
  "updatedAt": "2026-06-20T10:30:00Z",

  "project": {
    "id":          "uuid-v4",
    "name":        "My Edit",
    "frameRate":   30,
    "resolution":  { "width": 1920, "height": 1080 },
    "audioSampleRate": 48000,
    "duration":    "00:01:30.000"
  },

  "mediaBin": [
    {
      "id":   "uuid",
      "kind": "video" | "audio" | "image",
      "path": "media/clip_001.mp4",
      "proxyPath": null,
      "duration": "00:00:12.500",
      "metadata": { ...codec-specific... }
    }
  ],

  "tracks": [
    {
      "id":   "uuid",
      "kind": "video" | "audio",
      "index": 0,
      "locked":   false,
      "muted":    false,
      "clips": [
        {
          "id":     "uuid",
          "mediaId":"uuid",
          "in":     "00:00:01.000",
          "out":    "00:00:05.000",
          "position":"00:00:00.000",
          "speed":  1.0,
          "effects": [ "effect-uuid", ... ]
        }
      ]
    }
  ],

  "effects": [
    {
      "id":      "uuid",
      "kind":    "blur" | "color-correct" | "sharpen" | ...,
      "enabled": true,
      "params":  { ...kind-specific key/value... }
    }
  ],

  "markers": [
    { "id": "uuid", "time": "00:00:10.000", "label": "Cut point", "color": "red" }
  ]
}
```

## Rules

1. **IDs are UUIDv4** in lowercase canonical form. Stable across saves.
2. **Times are ISO-8601 durations** (`HH:MM:SS.fff`) for human readability; the
   editor internally normalizes to `int64_t` ticks (10 MHz default).
3. **Media paths are project-relative** when possible; absolute only when the
   media is outside the project tree. Missing media is flagged but the file
   still saves.
4. **Schema is forward-compatible**: unknown fields are preserved on round-trip
   (so newer editors can edit files from older versions).
5. **Atomic save**: write to `.bsp.tmp`, fsync, rename to `.bsp`. A crash leaves
   the original `.bsp` intact plus a `.bsp.tmp` to recover from.

## Backwards compatibility

| Version | Status       | Notes                                    |
|---------|--------------|------------------------------------------|
| 0.1     | current      | initial schema                           |

Future minor versions MUST be readable by older editors; future major versions
MAY break the schema and the editor should warn the user on open.

## Open questions (track in #74)

- Should `.bsp` bundle media (zip-style container) or always reference external
  media? Decision pending — leaning toward external references + an explicit
  "bundle project" command.
- Should effects be inline (current draft) or referenced by ID from a library?
  Draft uses inline so projects are self-contained.