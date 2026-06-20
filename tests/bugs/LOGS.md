# Bug Logging Guide

**Project:** Beetle Studio
**Owner:** Lisa Martinez (QA Lead)
**Version:** 1.0.0
**Last Updated:** June 2026

---

## Log Format

All bug reports must follow this structured format to ensure consistent tracking and reproduction.

---

## Required Fields

| Field | Description | Example |
|---|---|---|
| **Bug ID** | Auto-assigned from issue tracker | BUG-2026-0042 |
| **Date** | ISO 8601 date of discovery | 2026-06-19 |
| **Severity** | Critical / High / Medium / Low | High |
| **Reporter** | Name of person who found it | Lisa Martinez |
| **Component** | Affected module | Timeline / Audio / Effects / UI / Codecs |
| **Version** | Build version where found | 0.1.0-alpha.23 |
| **OS** | Operating system and version | Windows 11 23H2 |
| **GPU** | Graphics card (if relevant) | NVIDIA RTX 4070 |
| **Repro Steps** | Numbered steps to reproduce | See template below |
| **Expected** | What should happen | Video plays smoothly |
| **Actual** | What actually happens | Playback stutters at 4K |
| **Logs** | Attached log files | crash.dmp, debug.log |
| **Screenshot** | Visual evidence | screenshot.png |

---

## Example Entry

`
Bug ID:      BUG-2026-0042
Date:        2026-06-19
Severity:    High
Reporter:    Lisa Martinez
Component:   Timeline
Version:     0.1.0-alpha.23
OS:          Windows 11 23H2
GPU:         NVIDIA RTX 4070

Repro Steps:
1. Open project with 3+ video tracks
2. Add a cross-dissolve transition between clips on track 1
3. Scrub the playhead across the transition
4. Observe playback in the preview viewport

Expected: Smooth transition preview at project framerate
Actual:   Preview drops to ~5fps during transition, UI freezes for ~2s

Logs: Attached debug.log showing GPU memory spike
Screenshot: timeline_freeze.png
`

---

## Log Retention Policy

| Log Type | Retention | Storage |
|---|---|---|
| Crash dumps (.dmp) | 90 days | Issue tracker attachments |
| Debug logs (.log) | 30 days | Issue tracker attachments |
| Performance traces | 60 days | Shared drive |
| Screenshots | Indefinite | Issue tracker |
| Video recordings | 30 days | Shared drive |

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Lisa Martinez | Initial bug logging guide |