# Troubleshooting Guide

**Project:** Beetle Studio  
**Owner:** Tom Anderson (Technical Writer) — with Lisa Martinez (QA)  
**Reviewers:** Kirk Beka (CTO), Mooned Dev (CEO)
**ISO Standards:** ISO/IEC 25010:2023 (reliability, usability), ISO/IEC 14764:2022 (maintenance)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Common issues and step-by-step fixes |
| **Diátaxis form** | How-to guide |
| **Primary audience** | All users, Tom Anderson, Lisa Martinez, Rachel Green |
| **Secondary audience** | Future maintainers and reviewers of this document |

---

## Overview

This guide helps you diagnose and fix the most common issues with Beetle Studio. Issues are grouped by phase: before you start, installation, startup, playback, export, and account. For each issue, you'll find the cause and a step-by-step solution.

## Contents

- [Before You Start](#before-you-start)
- [Installation Issues](#installation-issues)
  - ["Windows protected your PC" warning on install](#windows-protected-your-pc-warning-on-install)
  - [Installation fails with error 0x80070005](#installation-fails-with-error-0x80070005)
- [Startup Issues](#startup-issues)
  - [Beetle Studio crashes on launch](#beetle-studio-crashes-on-launch)
  - [Beetle Studio runs but viewport is black](#beetle-studio-runs-but-viewport-is-black)
- [Playback Issues](#playback-issues)
  - [Preview playback stutters or drops frames](#preview-playback-stutters-or-drops-frames)
  - [Audio plays but video doesn't sync](#audio-plays-but-video-doesnt-sync)
- [Performance Issues](#performance-issues)
  - [High RAM usage (> 16 GB)](#high-ram-usage-16-gb)
  - ["Out of GPU memory" error](#out-of-gpu-memory-error)
- [Export Issues](#export-issues)
  - [Export fails at 99%](#export-fails-at-99)
  - [Exported video is larger than expected](#exported-video-is-larger-than-expected)
- [Crash During Save](#crash-during-save)
  - ["Save failed — file is locked"](#save-failed-file-is-locked)
- [Where to Get More Help](#where-to-get-more-help)
- [Collecting Debug Information](#collecting-debug-information)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

## Before You Start

- **Check your version:** Help → About Beetle Studio (vX.Y.Z)
- **Update Beetle Studio:** Help → Check for Updates — many issues are fixed in newer versions
- **Restart Beetle Studio** before troubleshooting most issues

---

## Installation Issues

### "Windows protected your PC" warning on install

**Cause:** SmartScreen hasn't yet recognized Beetle Studio's new code signing certificate.  
**Solution:**
1. Click **More info** → **Run anyway**
2. After installation, SmartScreen reputation builds automatically (~1,000 installs)
3. If issue persists, verify code signing: `signtool verify /pa BeetleStudioSetup.exe`

### Installation fails with error 0x80070005

**Cause:** Insufficient permissions to write to the target directory.  
**Solution:**
1. Right-click the installer → **Run as administrator**
2. Or choose a user-writable directory as the install path

---

## Startup Issues

### Loader checks (what the splash actually verifies)

When Beetle Studio starts, the splash screen runs **17 real system checks in order** before
the main window opens. Each check is a genuine OS API call — not a stub — and the splash
will not close until every check has either populated its result line or explicitly timed
out. Per-check timeout is **5 seconds** and the overall splash-verify timeout is **30 seconds**;
if either elapses the check is reported as `TIMEOUT` (not `OK`/`FAIL`) so the runbook is fully
deterministic for SREs triaging support tickets.
out. The full list:

| # | Check | What it verifies | Why it matters |
|---|---|---|---|
| 1 | CPU | `SYSTEM_INFO` core count | Thread pool sizing for render workers |
| 2 | RAM | `GlobalMemoryStatusEx` total/free | Pre-allocation budget for timeline cache |
| 3 | GPU | DXGI `EnumAdapters1` first adapter + VRAM | Adapter-aware shader compilation |
| 4 | DirectX 12 | `D3D12CreateDevice` succeeds on the chosen adapter | Hard prerequisite for the renderer |
| 5 | Internet | WinINet 200 KB download from `speed.cloudflare.com` | Affects CDN-fetched cloud assets and license |
| 6 | Project integrity | All required `splash*.png` + `BeetleStudio.exe` present and size > 0 | Catches broken installs before load |
| 7 | Audio device | `waveOutGetNumDevs` | A/V sync requires an audio device |
| 8 | Disk space | `GetDiskFreeSpaceExW` on the install volume | Scratch disk for the cache |
| 9 | Locale | `GetUserDefaultLocaleName` | UI language resolution |
| 10 | System time | `GetSystemTime` formatted as `YYYY-MM-DD HH:MM UTC` | Prevents license clock drift |
| 11 | Write access | `CreateFileW` test file in `%LOCALAPPDATA%\Mooned Dev\Beetle Studio\__writetest.tmp` | Cache and crash-dump writes |
| 12 | Vulkan | `LoadLibraryW("vulkan-1.dll")` + `vkGetInstanceProcAddr` | Optional GPU backend for effects |
| 13 | VC++ runtime | `vcruntime140.dll` + `msvcp140.dll` in `System32` | Static-link runtime for our native build |
| 14 | Cloudflare WARP | `HKLM\SOFTWARE\Cloudflare` registry key + `CloudflareWARP` service state | WARP is the recommended way to reach the asset CDN |
| 15 | Driver updates | `wuauserv` service state + last-check timestamp from `HKLM\...\WindowsUpdate\Auto Update\Results\Detect`. If the service is stopped, Beetle Studio tries to **start it** so the OS can pull driver updates. | Outdated GPU drivers cause DX12/Vulkan crashes |
| 16 | Power plan | `PowerGetActiveScheme` + `PowerReadFriendlyName` from `powrprof.dll` | Balanced/Battery Saver throttles render — we flag it |
| 17 | Windows version | `RtlGetVersion` from `ntdll.dll` (not the lying `GetVersionEx`) | Build number must be ≥ 18362 |

If a check fails, the line is rendered with a ✗ in the splash and the loader still proceeds
to the main window — but a **WARN** row will be visible until you fix the underlying issue.

### Beetle Studio crashes on launch

**Try in order:**

1. **Reset user settings** (rename the settings folder):
   ```powershell
   # Rename settings folder — Beetle Studio will recreate defaults
   Rename-Item "$env:APPDATA\Mooned Dev\Beetle Studio\config" "config.bak"
   ```
2. **Check GPU drivers are up to date** — outdated NVIDIA/AMD drivers cause DX12 crashes.
   The splash's **Drivers** row shows the last successful Windows Update check date.
3. **Install the Visual C++ 2015–2022 Redistributable (x64)** — the splash's **VC++** row
   will say `missing vcruntime140` if it isn't present.
4. **Disable hardware acceleration** — run Beetle Studio with: `BeetleStudio.exe --no-gpu-accel`
5. **Submit a crash report** when prompted — this helps our team fix issues

### Beetle Studio runs but viewport is black

**Cause:** GPU rendering failed; software fallback not triggered.  
**Solution:**
1. Go to **Edit → Preferences → Performance**
2. Set **GPU Acceleration** to **Auto** or **DirectX 12**
3. Restart Beetle Studio

### "Drivers" row in the splash shows a warning

**Cause:** The `wuauserv` service is not running. Beetle Studio will try to start it
automatically, but on non-admin machines it can only report the failure.
**Solution:**
1. Open **Services** (`services.msc`)
2. Find **Windows Update** → right-click → **Start**
3. Run Windows Update and let it install pending driver updates
4. Restart Beetle Studio

### "Power" row in the splash shows a warning

**Cause:** The active power scheme is **Balanced** or **Power Saver**. These throttle the
GPU and CPU at the OS level, which will cause preview playback to drop frames.
**Solution:**
1. Open **Settings → System → Power**
2. Set the power mode to **Best performance**
3. Or pick the **High performance** / **Ultimate performance** plan via `powercfg /setactive`

### "WARP" row in the splash says "not installed"

**Cause:** Cloudflare WARP is not installed on the machine.
**Solution:**
1. Download WARP from [https://1.1.1.1](https://1.1.1.1)
2. Install and toggle WARP on
3. The splash's WARP row will switch to "installed, connected" the next time you start Beetle Studio


### Beetle Studio runs but viewport is black

**Cause:** GPU rendering failed; software fallback not triggered.  
**Solution:**
1. Go to **Edit → Preferences → Performance**
2. Set **GPU Acceleration** to **Auto** or **DirectX 12**
3. Restart Beetle Studio

---

## Playback Issues

### Preview playback stutters or drops frames

**Try these fixes (in order):**

1. **Lower preview resolution** — Timeline panel → click the **1/4** or **1/8** button above the viewport
2. **Reduce active effects** — disable heavy effects during editing, enable for export
3. **Clear GPU cache** — **Edit → Preferences → Cache → Clear GPU Cache**
4. **Check disk space** — Beetle Studio needs scratch disk space (set in Preferences)
5. **Disable other GPU applications** — close games, other editors running simultaneously

### Audio plays but video doesn't sync

**Cause:** Audio ahead of video.  
**Solution:**
1. **Edit → Preferences → Audio**
2. Set **Audio Offset** — try `-33ms` (adjust until sync is correct)
3. If using hardware encoding, ensure GPU drivers are current

---

## Performance Issues

### High RAM usage (> 16 GB)

**Cause:** Large projects with many media files loaded.  
**Solutions:**
1. **Close unused projects** — File → Close Project
2. **Lower preview quality** — 1/4 or 1/8 resolution
3. **Clear project browser thumbnails** — right-click in Project Browser → Clear Cache
4. **Increase virtual memory** — Windows System Settings → Advanced → Performance → Virtual Memory

### "Out of GPU memory" error

**Cause:** Too many textures loaded in GPU.  
**Solution:**
1. **Restart Beetle Studio** — GPU memory is freed on exit
2. **Close other GPU applications**
3. **Lower project resolution** temporarily

---

## Export Issues

### Export fails at 99%

**Cause:** Disk full, or output file is locked.  
**Solutions:**
1. **Check disk space** — Export needs ~2× the output file size free
2. **Change output location** — target folder may be read-only
3. **Kill any process locking the output file** — Task Manager → End process for that file
4. **Restart and retry**

### Exported video is larger than expected

**Cause:** High bitrate setting.  
**Solution:**
1. In Export Settings, reduce **Bitrate** or switch from **CBR** to **CRF**
2. For web, try **H.264 + H.265 hybrid** or **AV1** (better compression)

---

## Crash During Save

### "Save failed — file is locked"

**Solution:**
1. Ensure the project file isn't open in another application
2. Try **File → Save As** to save to a different location
3. Check Windows file permissions on the target folder

---

## Where to Get More Help

| Channel | Use For | Response Time |
|---|---|---|
| **In-app report** | Crashes and technical bugs | Monitored daily |
| **community.mooned.dev** | How-to questions, workflow tips | Community + team |
| **support@mooned.dev** | Account, licensing, billing issues | 1–2 business days |
| **Bug tracker** | Known issues and workarounds | Public list |

---

## Collecting Debug Information

When reporting a bug, include:

1. **Help → About Beetle Studio** — version and system info
2. **Help → Export Diagnostics** — creates a `.zip` with system logs
3. **GPU information** — DXDiag output: `dxdiag /t dxdiag.txt`
4. **Crash dump** — if prompted to send a crash report, click **Send Report**

---

*Grounded in: ISO/IEC 25010:2023 (Reliability, Recoverability), ISO/IEC 14764:2022 (Maintenance)*



---

## References

### Internal Documents

_No internal documents referenced._

### Standards & Frameworks

- ISO/IEC 12207:2017 (Systems and software engineering — Software life cycle processes)
- ISO/IEC 25010:2023 (Systems and software engineering — Quality requirements and evaluation)
- See [STYLE_GUIDE.md](./STYLE_GUIDE.md) for the full standards catalog

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Tom Anderson | Initial version |
| 1.0.1 | June 2026 | Tom Anderson | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Monthly
- **Reviewer:** Tom Anderson (Technical Writer) — with Lisa Martinez (QA)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type