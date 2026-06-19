# Test Strategy

**Project:** Beetle Studio  
**Owner:** Lisa Martinez (QA Lead)  
**Reviewers:** Kirk Beka (CTO), all engineering leads  
**ISO Standards:** ISO/IEC 12207:2017 (validation, verification), ISO/IEC 25010:2023 (reliability, functional suitability), ISO/IEC 14764:2022 (maintenance testing)  
**Version:** 1.0.0  
**Last Updated:** June 2026  

---


## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Test pyramid, coverage targets, severity levels, and release test gates |
| **Diátaxis form** | Reference |
| **Primary audience** | Lisa Martinez, all engineers, QA team |
| **Secondary audience** | Future maintainers and reviewers of this document |


---

## Overview

This document defines Beetle Studio's testing strategy -- the types of testing we do, how we do them, who owns them, and what quality gates must pass before any release. Per **ISO/IEC 12207:2017 section 6.3**, verification and validation are required activities throughout the software lifecycle. Testing is our primary verification mechanism, and this strategy ensures we test the right things, at the right level, with the right coverage. Testing is also a key input to post-release maintenance -- per **ISO/IEC 14764:2022**, regression testing prevents defects from reappearing as the product evolves.

## Contents

- [Testing Principles](#testing-principles)
- [Test Pyramid](#test-pyramid)
- [Test Types](#test-types)
  - [1. Unit Tests](#1-unit-tests)
  - [2. Integration Tests](#2-integration-tests)
  - [3. Smoke Tests](#3-smoke-tests)
  - [4. Regression Tests](#4-regression-tests)
  - [5. Performance Tests](#5-performance-tests)
  - [6. Exploratory Testing](#6-exploratory-testing)
  - [7. Accessibility Tests](#7-accessibility-tests)
  - [8. Beta Testing](#8-beta-testing)
- [Coverage Requirements](#coverage-requirements)
  - [Per Module](#per-module)
  - [Overall](#overall)
- [Bug Severity Scale](#bug-severity-scale)
  - [Severity Examples by Subsystem](#severity-examples-by-subsystem)
- [Bug Investigation: Expected vs Actual + Before/After Loop](#bug-investigation-expected-vs-actual-beforeafter-loop)
  - [The Self-Question Loop](#the-self-question-loop)
  - [The Fix Loop](#the-fix-loop)
  - [Required Bug Report Template](#required-bug-report-template)
- [Bug Report](#bug-report)
  - [1. What I Was Doing (context)](#1-what-i-was-doing-context)
  - [2. Expected Behavior (what the app should have done)](#2-expected-behavior-what-the-app-should-have-done)
  - [3. Actual Behavior (what the app actually did)](#3-actual-behavior-what-the-app-actually-did)
  - [4. Hypothesis (why it might be doing the wrong thing)](#4-hypothesis-why-it-might-be-doing-the-wrong-thing)
  - [5. Steps to Reproduce](#5-steps-to-reproduce)
  - [6. Environment](#6-environment)
  - [7. Visual Evidence](#7-visual-evidence)
  - [8. Fix Loop](#8-fix-loop)
  - [Before/After Image Conventions](#beforeafter-image-conventions)
  - [Image-Aware Bug Review (engineer)](#image-aware-bug-review-engineer)
  - [Self-Question Checklist (use this every time)](#self-question-checklist-use-this-every-time)
  - [Tooling](#tooling)
  - [Anti-Patterns (rejected at review)](#anti-patterns-rejected-at-review)
  - [Loop Metric (track in `tests/bugs/LOGS.md`)](#loop-metric-track-in-testsbugslogsmd)
- [Test Environments](#test-environments)
- [CI Test Pipeline](#ci-test-pipeline)
- [Release Test Pass](#release-test-pass)
- [Adding Tests to the Suite](#adding-tests-to-the-suite)
  - [For Engineers](#for-engineers)
  - [Test File Locations](#test-file-locations)
- [UI Test Tools](#ui-test-tools)
  - [Tool Selection Matrix](#tool-selection-matrix)
  - [WinAppDriver](#winappdriver)
  - [FlaUI](#flaui)
  - [PyAutoGUI](#pyautogui)
  - [UI Test Coverage Strategy](#ui-test-coverage-strategy)
  - [Stability & Flakiness](#stability-flakiness)
  - [Accessibility Prerequisite](#accessibility-prerequisite)
- [Version History](#version-history)
  - [Change Log](#change-log)
  - [Review Cadence](#review-cadence)

---


---


---

## Testing Principles

1. **Test early and often** — bugs found in development cost 10× less than bugs found after release
2. **Automate what repeats** — CI runs automated tests on every commit; manual testing focuses on exploratory and usability work
3. **Coverage is a means, not an end** — 100% line coverage means nothing if the tests don't catch real failures
4. **Reproducibility is non-negotiable** — every failing test must have a clear reproduction case; flaky tests are treated as highest priority bugs
5. **Performance is a feature** — slow playback and stuttering exports are bugs, not preferences

---

## Test Pyramid

We follow a test pyramid model. Each layer is broader than the one above it.

```
                    ┌──────────────────┐
                    │   E2E / SYSTEM   │  ← Few, slow, high confidence
                    │  (automated +   │     User workflows, full codec pipeline
                    │   manual beta)  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  INTEGRATION      │  ← Moderate, subsystem boundaries
                    │  (automated)      │     UI ↔ Engine, Engine ↔ Codec,
                    └────────┬─────────┘     Cloud sync, plugin loading
                             │
              ┌──────────────▼──────────────┐
              │         UNIT TESTS          │  ← Many, fast, narrow
              │         (automated)          │    Data model logic, codec parsing,
              └──────────────────────────────┘    math functions, undo/redo commands
```

---

## Test Types

### 1. Unit Tests

| Property | Detail |
|---|---|
| **Scope** | Single function, class, or module in isolation |
| **Framework** | GoogleTest (C++ for engine/UI), custom test harness |
| **Speed** | < 5ms per test; full suite < 30 seconds |
| **When** | Every PR and push to `main` |
| **Coverage gate** | ≥ 80% line coverage per module; ≥ 90% for critical modules |
| **Owner** | Feature engineer writes tests; Lisa Martinez reviews |

**Critical modules (≥ 90% coverage required):**
- Timeline data model (`timeline/DATA_MODEL.md`)
- Undo/redo command system
- Color space conversion functions
- Audio sync / latency calculations
- Clip trimming and splitting algorithms

**Standard modules (≥ 80% coverage):**
- FFmpeg wrapper / codec interface
- Effect parameter parsing
- Project save/load serialization
- SWID tag generation

### 2. Integration Tests

| Property | Detail |
|---|---|
| **Scope** | Two or more modules working together |
| **Framework** | GoogleTest + mocking (GoogleMock) |
| **Speed** | < 500ms per test; suite < 5 minutes |
| **When** | Every PR; nightly full suite on `main` |
| **Owner** | Feature engineer writes tests |

**Key integration test scenarios:**

| Scenario | Modules Involved | Validates |
|---|---|---|
| Timeline clip add/remove | Data Model + Undo | State consistency after command |
| Effect applied to clip | Engine + Effects + Data Model | Effect chain updates correctly |
| Project save/load roundtrip | Data Model + File I/O | All data serializes correctly |
| Plugin loaded and rendered | Plugin Host + OpenFX SDK + Engine | Plugin output integrated |
| Cloud sync conflict | Backend API + Data Model | Conflict resolution logic |
| Export to file | Engine + Codec + File I/O | File is valid and playable |

### 3. Smoke Tests

| Property | Detail |
|---|---|
| **Scope** | Core application launch and basic user workflows |
| **Framework** | Automated via Playwright or custom C++ harness |
| **Speed** | < 2 minutes per run |
| **When** | Every CI build (main + release); post-install on fresh system |
| **Owner** | Lisa Martinez |

**Smoke test checklist (automated):**

- [ ] Application launches without crash
- [ ] New project created and saved
- [ ] Media imported (MP4 file loaded)
- [ ] Clip placed on timeline
- [ ] Timeline playhead moves
- [ ] Playback starts and runs ≥ 5 seconds
- [ ] Effect applied to clip
- [ ] Effect removed from clip
- [ ] Project saved and reopened
- [ ] Clean uninstall

### 4. Regression Tests

| Property | Detail |
|---|---|
| **Scope** | All known bugs that have been fixed |
| **Framework** | Automated test harness + manual checklist |
| **When** | Before every release (automated); before every beta (manual) |
| **Owner** | Lisa Martinez maintains suite; engineers add regression tests when fixing bugs |

**Rule:** Every confirmed bug that becomes a fix must have a regression test. If a bug doesn't have a reproducible test, it isn't fully closed.

**Regression test tracker:** Managed in the bug tracker (Linear). Tags: `regression-test`.

### 5. Performance Tests

| Property | Detail |
|---|---|
| **Scope** | Benchmarks defined in [`PERFORMANCE_BENCHMARKS.md`](../PERFORMANCE_BENCHMARKS.md) |
| **Framework** | Custom C++ benchmark harness + RenderDoc/PIX for GPU profiling |
| **When** | Every CI build (fast checks); alpha and beta releases (full suite) |
| **Owner** | Lisa Martinez measures; James Park + Sophie Williams analyze |
| **Regression threshold** | ≥ 20% miss on any target → release blocker |

See [`PERFORMANCE_BENCHMARKS.md`](../PERFORMANCE_BENCHMARKS.md) for the full benchmark suite.

### 6. Exploratory Testing

| Property | Detail |
|---|---|
| **Scope** | Unscripted; tester uses the application as a user would |
| **When** | Every sprint; before every beta release |
| **Owner** | Lisa Martinez + beta testers |
| **Documentation** | Session report in bug tracker per session |

Exploratory testing is where we find the bugs that scripted tests miss — unexpected interactions, UI inconsistencies, and edge cases that only appear under real-world usage.

### 7. Accessibility Tests

| Property | Detail |
|---|---|
| **Scope** | WCAG 2.1 AA compliance |
| **Framework** | Automated (axe-core) + manual (NVDA, Windows Narrator) |
| **When** | Every release |
| **Owner** | Lisa Martinez automates; Alex Chen + QA team manually |

See [`ACCESSIBILITY_COMPLIANCE.md`](../ACCESSIBILITY_COMPLIANCE.md) for the full compliance checklist.

### 8. Beta Testing

| Property | Detail |
|---|---|
| **Scope** | Real-world usage by selected external users |
| **When** | Per beta program cycle (see [`BETA_PROGRAM_GUIDE.md`](../BETA_PROGRAM_GUIDE.md)) |
| **Owner** | Lisa Martinez coordinates; Rachel Green manages community |

Beta testing is our primary validation activity before stable releases. See [`BETA_PROGRAM_GUIDE.md`](../BETA_PROGRAM_GUIDE.md).

---

## Coverage Requirements

### Per Module

| Module | Unit Coverage | Integration Tests Required |
|---|---|---|
| Timeline data model | ≥ 90% | ✅ Clip add/remove, undo/redo, save/load |
| Audio engine | ≥ 80% | ✅ Audio/video sync, VST loading |
| Rendering pipeline | ≥ 70% | ✅ Frame render from decoded buffer |
| Codec interface | ≥ 80% | ✅ Decode → frame buffer, seek accuracy |
| Effects pipeline | ≥ 70% | ✅ Effect chain execution, parameter updates |
| Project save/load | ≥ 80% | ✅ Full roundtrip, backwards compatibility |
| UI state management | ≥ 60% | ✅ Panel state save/restore |
| Cloud sync | N/A (tested manually) | ✅ Conflict resolution |

### Overall

| Metric | Target |
|---|---|
| **Total line coverage** | ≥ 70% |
| **Critical path coverage** | 100% |
| **New code coverage (per PR)** | ≥ 80% |

Coverage reports are generated by `llvm-cov` and published to CI artifacts. Coverage regressions block PR merge.

---

## Bug Severity Scale

Per **ISO/IEC 25010:2023**, reliability includes the ability to recover from failures. Bug severity drives how we prioritize fixes.

| Severity | Definition | Response SLA | Release Impact |
|---|---|---|---|
| **S0 — Critical** | Application crash, data loss, security vulnerability | Fix within 24 hours | Hotfix; release blocked |
| **S1 — Major** | Core feature completely broken; export fails entirely; playback crashes | Fix within 3 days | Release blocked |
| **S2 — Minor** | Feature impaired but workaround exists; non-critical export failure | Fix within sprint | Release delayed if < 3 S2s remaining |
| **S3 — Cosmetic** | Visual glitch, label typo, minor UI inconsistency | Fix in next release | Never blocks release |

### Severity Examples by Subsystem

| Bug | Severity | Reason |
|---|---|---|
| Timeline crashes when trimming clip edge | S0 | Crash |
| Export produces corrupt file (not playable) | S0 | Data loss |
| H.264 decode fails silently | S1 | Core codec broken |
| Timeline playhead shows wrong timecode | S1 | User cannot trust output |
| Audio crackles on playback with 20+ tracks | S1 | Core audio broken |
| Color wheel doesn't respond to mouse drag | S2 | Workaround: type value manually |
| Preview viewport shows subpixel aliasing | S3 | Minor visual |
| "Import" button tooltip is incorrect | S3 | Cosmetic |

---

## Bug Investigation: Expected vs Actual + Before/After Loop

Every bug report — from internal QA, engineers, beta testers, or users — must follow this **investigation loop**. The goal: force the tester to **observe carefully** (what is the app actually doing right now?), **describe the expected behavior** (what should the app be doing in front of the user?), and **provide visual evidence** so the engineer can confirm the bug without reproducing it themselves. Then we **loop until the fix is verified**.

### The Self-Question Loop

For every bug, before filing, ask yourself these questions in order. If you can't answer any of them, you don't fully understand the bug yet — go back to the app and observe more.

| # | Question | Why it matters |
|---|---|---|
| 1 | **What am I looking at right now?** Describe the exact UI state — which screen, which panel, which control has focus, what is selected. | Anchors the report. If you can't describe the screen, you haven't isolated the bug. |
| 2 | **What is the app doing right now?** Describe the actual behavior in 1-2 sentences. What moved, what changed, what didn't change. | The "actual" half of the diff. |
| 3 | **What should the app be doing here?** Describe the expected behavior, grounded in the spec, the docs, or the natural user intent. | The "expected" half of the diff. If you can't articulate this, you don't know whether it's a bug or a misunderstanding. |
| 4 | **Why is it doing the wrong thing?** Hypothesize the cause (1-2 sentences). "The color wheel handler isn't subscribed to the slider value change event." | Engineers start from your hypothesis, not zero. Even a wrong hypothesis narrows the search. |
| 5 | **Can I capture it visually?** Screenshot the actual state, and (if possible) a "what it should look like" mock or reference screenshot. | Visual evidence is the only way to communicate bugs that involve layout, color, alignment, animation, or visual state. |

### The Fix Loop

Once a bug is filed, the fix is verified by an **iterative loop**, not a one-shot. We keep going until the actual matches the expected.

```
              +------------------+
              | Bug filed with   |
              | expected/actual  |
              | + before image   |
              +--------+---------+
                       |
                       v
              +------------------+
              | Engineer         |
              | reproduces +     |
              | proposes fix     |
              +--------+---------+
                       |
                       v
              +------------------+
              | Fix implemented  |
              | + "after" image  |
              | captured         |
              +--------+---------+
                       |
                       v
              +------------------+
              | Tester compares  |
              | before vs after  |
              | vs expected      |
              +--------+---------+
                       |
            +----------+----------+
            |                     |
   does the new behavior          still doesn't match
   match the expected?             expected? -> back to
            |                      "Engineer reproduces"
            v                      with new before image
     +------+------+               and updated hypothesis
     | Test passes |
     | + mark bug  |
     |   as Resolved|
     +-------------+
```

**Loop termination rule:** the bug is only closed when a tester (the same one or a different one) confirms that the **after image** matches the **expected description** under the same repro conditions. "I think it's fixed" is not a fix.

### Required Bug Report Template

Every bug — internal, beta, or user — must include these fields. Copy-paste this template into the bug tracker.

```markdown
## Bug Report

**Title:** [one-line summary]
**Severity:** S0 / S1 / S2 / S3
**Reporter:** [name]
**Date:** [YYYY-MM-DD]
**Version:** [Beetle Studio version + commit hash if known]

---

### 1. What I Was Doing (context)

[Describe the user flow / scenario. Where in the app, what just before, what was selected.]

### 2. Expected Behavior (what the app should have done)

[Describe what should happen. Reference the spec, the user docs, or the principle of least surprise.
If you can point to a doc section or a spec line, do.]

### 3. Actual Behavior (what the app actually did)

[Describe what actually happened. Quote error messages verbatim. Note exact wrong values if any.]

### 4. Hypothesis (why it might be doing the wrong thing)

[Your best guess at the cause. Code path, control, state, timing. Be specific.]

### 5. Steps to Reproduce

1. [Step 1]
2. [Step 2]
3. [Step 3]
4. [Observe: expected X, got Y]

### 6. Environment

- **OS:** [Windows 11 23H2]
- **Build:** [Beetle Studio 1.0.0-beta.3 (commit abc123)]
- **GPU:** [NVIDIA RTX 3060]
- **Project file:** [attach .beetle file or describe]
- **Media files:** [attach or describe source clip]

### 7. Visual Evidence

**BEFORE — actual state (screenshot or short recording):**
[Attach `before.png` or link to `tests/bugs/<bug-id>/before.png`]

**REFERENCE — what it should look like (optional but strongly recommended for UI bugs):**
[Attach `expected.png` showing the correct behavior, or annotate a Figma link]

**Caption for before image:** [What the tester was seeing; e.g. "Color wheel reset to default after dragging to red"]
**Caption for expected image:** [What it should be; e.g. "Color wheel should stay at red after release"]

### 8. Fix Loop

| Iteration | Date | Engineer | Fix Description | After Image | Verified? |
|---|---|---|---|---|---|
| 1 | YYYY-MM-DD | [name] | [fix description] | `after-1.png` | [ ] Yes / [ ] No — see notes |
| 2 | YYYY-MM-DD | [name] | [re-fix description] | `after-2.png` | [ ] Yes / [ ] No — see notes |

**Close-out:** the bug is only closed when "Verified" is checked AND the after image matches the expected behavior described in section 2.
```

### Before/After Image Conventions

- **File naming:** `tests/bugs/<BUG-ID>/before.png`, `after-1.png`, `after-2.png`, etc.
- **Format:** PNG (lossless), 1:1 with the relevant UI area, 1080p+ for full-screen shots
- **Annotations:** Use arrows, circles, highlights to mark the bug. Tools: ShareX, Greenshot, or built-in Snip & Sketch
- **For animation/timing bugs:** short screen recording (MP4 or GIF), under 15 seconds
- **For "what it should look like":** mock in Figma, screenshot from a working version, or screenshot from a reference product (with attribution)

### Image-Aware Bug Review (engineer)

When the engineer picks up the bug, they must:

1. **Read section 2 first** (expected). Form a mental model of what correct looks like.
2. **Look at the before image** with section 2 in mind. Confirm the bug visually matches the description.
3. **Read the hypothesis** (section 4) and either confirm or counter-hypothesize.
4. **After implementing the fix, capture `after-1.png`** under the same conditions (same project, same OS, same zoom).
5. **Hand back to the tester with the after image** — do not self-close.

### Self-Question Checklist (use this every time)

Before you click "Submit" on a bug report, run through this:

- [ ] I can describe the exact UI state at the moment of the bug
- [ ] I have a clear "expected" that is grounded in docs or natural intent
- [ ] I have a clear "actual" that is observable and reproducible
- [ ] I have a hypothesis (even if I'm wrong, it's a starting point)
- [ ] I have a before screenshot or recording
- [ ] For UI bugs, I have an "expected" reference image or doc link
- [ ] My repro steps are deterministic (same input → same wrong output)
- [ ] I noted the build, OS, GPU, and project file

If any box is unchecked, the report is not ready.

### Tooling

| Tool | Purpose | Where |
|---|---|---|
| **Built-in Snip & Sketch** (`Win+Shift+S`) | Quick screenshots during testing | Windows default |
| **ShareX** | Annotated screenshots, scrolling capture, GIF recording | `tools/sharex/` config in repo |
| **Greenshot** | Lightweight screenshot + annotation | alt if ShareX is overkill |
| **ScreenToGif** | Short MP4/GIF recordings for animation bugs | alt for ShareX |
| **Figma** | "Expected" reference mockups for UI bugs | existing team Figma |

### Anti-Patterns (rejected at review)

| Anti-pattern | Why we reject |
|---|---|
| "It looks wrong" with no image or specific area | We can't act on vibes |
| Expected = "it should work" | Expected must be specific |
| Bug filed with no repro | Can't verify the fix; will be auto-closed after 14 days |
| Fix closed without an after image | No evidence the fix works |
| Tester says "I think it's fixed" | Not a fix — must re-test under the same repro |
| Hypothesis = "I don't know" | Forces the reporter to look at the code or ask an engineer — that's the point |
| Screenshot at a random zoom that hides the bug | Must show the bug, not hide it |

### Loop Metric (track in `tests/bugs/LOGS.md`)

| Metric | Target | Why |
|---|---|---|
| Average iterations per bug | < 2.5 | Most bugs should fix first try |
| Bugs closed without after image | 0 | Process enforcement |
| Bugs re-opened after close | < 5% | Means the fix loop was insufficient |
| Mean time from file to first fix attempt | < 24 h (S1), < 72 h (S2) | Response time |

---

## Test Environments

| Environment | OS | GPU | RAM | Use Case |
|---|---|---|---|---|
| **Minimum spec** | Windows 10 1903 | GTX 1660 Super | 8 GB | Performance lower bound |
| **Recommended spec** | Windows 11 | RTX 3060 | 32 GB | Standard QA testing |
| **High-end spec** | Windows 11 | RTX 4090 | 64 GB | Performance upper bound |
| **Clean VM** | Windows 10 22H2 | Virtual GPU | 8 GB | Install/uninstall testing |
| **CI runner** | Windows Server 2022 | None (headless) | 16 GB | Automated tests only |

---

## CI Test Pipeline

```
┌──────────────────────────────────────────────────────────┐
│                   CI TEST PIPELINE                        │
│                                                           │
│  ┌──────────┐                                           │
│  │ PR/Push  │                                           │
│  └────┬─────┘                                           │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐                                           │
│  │  Build   │ ← CMake + MSVC                            │
│  └────┬─────┘                                           │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐                                           │
│  │ Unit +   │ ← ~3 min; blocks on failure               │
│  │Integration│                                           │
│  └────┬─────┘                                           │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐                                           │
│  │  Smoke   │ ← ~2 min; blocks on failure               │
│  │  Tests   │                                           │
│  └────┬─────┘                                           │
│       │                                                  │
│       ▼                                                  │
│  ┌──────────┐                                           │
│  │Coverage  │ ← Reports to CI artifacts                   │
│  │ Report  │                                           │
│  └──────────┘                                           │
│                                                           │
│  Nightly:                                               │
│  ┌──────────┐                                           │
│  │ Full Perf│ ← Performance benchmarks                    │
│  │ Benchmarks│                                          │
│  └──────────┘                                           │
└──────────────────────────────────────────────────────────┘
```

---

## Release Test Pass

Before any release, Lisa Martinez signs off on:

| Test Type | Alpha | Beta | Stable Release |
|---|---|---|---|
| Unit tests | ✅ | ✅ | ✅ |
| Integration tests | ✅ | ✅ | ✅ |
| Smoke tests | ✅ | ✅ | ✅ |
| Regression tests | ✅ | ✅ | ✅ |
| Performance benchmarks | ✅ | ✅ | ✅ |
| Exploratory testing | ✅ | ✅ | ✅ |
| Accessibility audit | ✅ | ✅ | ✅ |
| Clean install test | — | ✅ | ✅ |
| Upgrade install test | — | ✅ | ✅ |
| Beta user feedback | — | ✅ | ✅ |

No release ships without all applicable tests passing.

---

## Adding Tests to the Suite

### For Engineers

When you open a PR:

1. **Unit tests required** for any new logic (functions, data transformations, algorithms)
2. **Integration tests required** for any cross-module interaction
3. **Regression test required** for any bug fix
4. Run `scripts/run_tests.ps1` locally before pushing
5. Coverage must not regress by > 5% without justification

### Test File Locations

```
src/
├── Engine/tests/          ← Unit tests for engine modules
│   ├── Timeline_test.cpp
│   ├── AudioSync_test.cpp
│   └── CodecWrapper_test.cpp
├── UI/tests/             ← Unit tests for UI logic
├── tests/                ← Integration tests
│   ├── ProjectRoundtrip_test.cpp
│   ├── EffectChain_test.cpp
│   └── PluginLoad_test.cpp
scripts/
├── run_unit_tests.ps1    ← Run unit + integration tests
├── run_smoke_tests.ps1   ← Run smoke test harness
└── run_perf_tests.ps1    ← Run performance benchmarks

---

## UI Test Tools

Beetle Studio is a C++/Qt6 Windows desktop app. Our test pyramid already covers unit, integration, smoke, and regression tests. For **UI-level testing** (driving the real Windows app, clicking through the UI, verifying real Win32 behavior), we use the following tools. Each fills a different gap.

### Tool Selection Matrix

| Tool | Stack | What it tests | When to use | Owner |
|---|---|---|---|---|
| **WinAppDriver** | C#/WinAppDriver server + JSON Wire Protocol | Real Windows UI (Win32, WinForms, WPF, UWP — and Qt via MSAA/UIA) | End-to-end UI flows on real Windows VMs; cross-app scenarios (File Explorer, Windows Store, drag-and-drop) | Lisa Martinez (QA) |
| **FlaUI** | .NET library wrapping UIAutomation | Real Windows UI with .NET-native assertions | When you want C# test code that's cheaper to write than WinAppDriver; custom Qt UIA providers | Lisa Martinez (QA) |
| **PyAutoGUI** | Python, cross-platform | Real OS-level mouse/keyboard, screenshots, image recognition | Quick smoke scripts; visual smoke checks; ad-hoc repro scripts; not for CI | Engineers + QA |
| **Qt Test (QTest)** | C++ Qt-native | Widgets, signals/slots, model/view | Already in our stack for unit-level widget tests | Engineers |
| **Playwright** | Node.js | Web UI (marketing site, user portal) | Web E2E (see [ACCESSIBILITY_COMPLIANCE.md Website Design Testing](../../ACCESSIBILITY_COMPLIANCE.md#website-design-testing)) | Web team |

### WinAppDriver

**What it is:** Microsoft's official UI automation server for Windows desktop apps. Speaks the JSON Wire Protocol (same as Selenium WebDriver) so you write tests in any language that has a WebDriver client.

**Why we picked it:**
- Official Microsoft tool, supports **Win32 + Qt 6** via the platform's UI Automation (UIA) providers
- Works with our existing test infrastructure (can run in CI Windows runners)
- Supports cross-app scenarios (drag from File Explorer, Windows Store launch, etc.)

**Requirements on our app:**
- Enable Qt's UIAutomation bridge: `QT_ACCESSIBILITY=1` env var, ship with `AccessibleFactory` plugin
- All custom widgets expose `QAccessibleObject` interfaces (we already do for the high-value widgets)
- Stable AutomationId / Name on every interactive control

**Test pattern:**

```csharp
// C# example using WinAppDriver + Appium.WebDriver
var options = new AppiumOptions();
options.AddAdditionalCapability("app", "C:\\Program Files\\Mooned Dev\\Beetle Studio\\BeetleStudio.exe");
options.AddAdditionalCapability("deviceName", "WindowsPC");
var driver = new WindowsDriver<WindowsElement>(new Uri("http://127.0.0.1:4723"), options);

var newProjectBtn = driver.FindElementByAccessibilityId("MainWindow.NewProject");
newProjectBtn.Click();
var projectName = driver.FindElementByAccessibilityId("NewProjectDialog.ProjectName");
projectName.SendKeys("My Test Project");
driver.FindElementByAccessibilityId("NewProjectDialog.Create").Click();
Assert.IsNotNull(driver.FindElementByName("Timeline")));
```

**Test file location:** `tests/ui/winappdriver/`

**CI integration:** runs on `windows-2022` GitHub Actions runner with WinAppDriver preinstalled; nightly on a real Windows 11 VM (BrowserStack or local).

### FlaUI

**What it is:** .NET library that wraps Microsoft's `UIAutomation` API directly. Native to .NET, no JSON-RPC hop, much faster than WinAppDriver for fine-grained assertions.

**Why we picked it:**
- Cheaper to write than WinAppDriver for in-process desktop test runs
- Better support for complex UIA patterns (virtualized items, custom UIA providers)
- Easier debugging (attach to the running process from Visual Studio)

**Test pattern:**

```csharp
using FlaUI.Core;
using FlaUI.UIA3;

var app = FlaUI.Core.Application.AttachOrLaunch(new ApplicationOptions
{
    Path = @"C:\Program Files\Mooned Dev\Beetle Studio\BeetleStudio.exe"
});
using (var automation = new UIA3Automation())
{
    var main = app.GetMainWindow(automation);
    var timeline = main.FindFirstDescendant(cf => cf.ByAutomationId("TimelinePanel"));
    Assert.IsNotNull(timeline);
    var clipCount = timeline.FindAllDescendants(cf => cf.ByControlType(ControlType.ListItem)).Length;
    Assert.Greater(clipCount, 0);
}
```

**Test file location:** `tests/ui/flaui/`

**When to prefer FlaUI over WinAppDriver:** in-process test runs (fast feedback), complex UIA pattern assertions, Windows-only CI with full Windows desktop session. For cross-process or cross-machine, use WinAppDriver.

### PyAutoGUI

**What it is:** Python library for cross-platform mouse/keyboard/screen automation. Works on Windows, macOS, Linux.

**Why we picked it:**
- **Fast to write** — perfect for ad-hoc repro scripts and visual smoke checks
- **No accessibility-tree dependency** — works even if our UIA providers are broken (which is exactly when you need a smoke test)
- Engineers can write a repro in 5 minutes without setting up C#/.NET

**What it's NOT good for:**
- CI — needs a real desktop session and is fragile to screen scaling
- Pixel-exact assertions (use Visual Regression instead)
- Cross-app scenarios with strict timing

**Test pattern (ad-hoc repro):**

```python
import pyautogui
import time

# Open the app
pyautogui.hotkey('ctrl', 'n')  # New Project
time.sleep(1)

# Screenshot for visual diff
pyautogui.screenshot('repro.png', region=(0, 0, 1920, 1080))

# Try the click sequence that crashes
pyautogui.click(x=640, y=400)  # Timeline playhead
pyautogui.hotkey('ctrl', 'shift', 'e')  # Export
```

**Test file location:** `tests/ui/pyautogui/` (engineer-local, not in CI). Use `repro_template.py` as a starting point — copy to `tests/ui/bugs/BUG-XXXX/repro.py`.

**When to use:** engineer reproducing a bug, QA creating a quick visual sanity check, **never** for assertions in CI.

### UI Test Coverage Strategy

| Layer | Tool | Coverage target |
|---|---|---|
| Widget unit tests | Qt Test (QTest) | All custom widgets have at least 1 unit test |
| UI flow smoke (CI) | WinAppDriver | Top 20 user flows per release |
| UI deep assertions (dev box) | FlaUI | Regression coverage for complex UIA patterns |
| Ad-hoc repro / visual smoke | PyAutoGUI | None (engineer-local only) |
| Web UI E2E | Playwright | See [ACCESSIBILITY_COMPLIANCE.md](../../ACCESSIBILITY_COMPLIANCE.md#website-design-testing) |

### Stability & Flakiness

| Anti-pattern | Why it fails | What to do instead |
|---|---|---|
| `time.sleep(1)` between actions | Non-deterministic on slow CI | Use WinAppDriver/FlaUI's `WaitUntilElementExists` with timeout |
| Pixel-exact screenshots in CI | DPI scaling, theme differences | Use UIA element queries (AutomationId, Name) |
| Hardcoded screen coordinates | Breaks on any UI change | Use accessibility tree navigation |
| No teardown if test fails | Leaves zombie app processes | Use `try/finally` with `app.Kill()` |

### Accessibility Prerequisite

**All UI tests depend on our app exposing a usable accessibility tree.** This is enforced by:
- Pre-commit lint: every `QWidget` subclass in `src/UI/` must override `accessibleName()` and `accessibleDescription()` (see [`ACCESSIBILITY_COMPLIANCE.md`](../../ACCESSIBILITY_COMPLIANCE.md))
- CI gate: axe-core-style scan on the live app tree using FlaUI (zero critical UIA violations blocks release)
```

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | June 2026 | Initial strategy — aligned with ISO/IEC 12207:2017 verification/validation, ISO/IEC 25010:2023, ISO/IEC 14764:2022 |

---

*Grounded in: ISO/IEC 12207:2017 §6.3 (Verification and Validation), ISO/IEC 25010:2023 (Reliability: Maturity, Availability, Recoverability, Fault Tolerance), ISO/IEC 14764:2022 (Maintenance Testing)*


---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Unknown owner | Initial version |
| 1.0.1 | June 2026 | Unknown owner | Added Scope & Audience block and Document Maintenance section per STYLE_GUIDE.md (ISO/IEC/IEEE 82079-1:2019 compliance) |

### Review Cadence

- **Next review:** Quarterly
- **Reviewer:** Lisa Martinez (QA Lead)
- **Cadence:** Per STYLE_GUIDE.md defaults for this document type