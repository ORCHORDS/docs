# Beetle Studio — Documentation Style Guide

**Project:** Beetle Studio
**Owner:** Tom Anderson (Technical Writer) — content; Kirk Beka (CTO) — technical authority
**Reviewers:** Mooned Dev (CEO), all domain leads
**ISO Standards:** ISO/IEC/IEEE 82079-1:2019 (preparation of information for use), ISO/IEC Directives Part 2 (document structure), ISO/IEC 12207:2017 (lifecycle), ISO/IEC 25010:2023 (quality), ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27034-1:2011
**Version:** 1.0.0
**Last Updated:** June 2026

---

## Overview

This guide is the canonical reference for how every document in `docs/` is structured, written, named, and maintained. Its purpose is to make our documentation **uniform, findable, and ISO-compliant** so any team member can read any document and know exactly what to expect.

All 41 documents in this directory conform to the rules defined here. When in doubt, follow this guide. When this guide and a document disagree, **this guide wins** — update the document.

This guide itself is governed by the same review cadence as any other document and may be amended by PR with approval from the document owner.

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | All Markdown documents under `docs/` in the Beetle Studio project |
| **Primary audience** | Internal team members (engineering, product, operations, marketing, leadership) |
| **Secondary audience** | External users reading user-facing docs (User Guide, Quick Start, FAQ, etc.) and third-party developers reading the OpenFX and VST plugin guides |
| **Out of scope** | Marketing web copy on `mooned.dev`, support tickets, internal chat, code comments — those have their own conventions |

---

## Authoritative ISO Standards

The conventions in this guide derive from three ISO documents and one widely-adopted framework. Authors should be familiar with them; reviewers should enforce compliance.

### ISO/IEC/IEEE 82079-1:2019 — Preparation of information for use

The primary international standard for the design and formulation of all types of instructions for use (user guides, manuals, product specs, technical documentation). It defines requirements on **content, structure, quality, process, media, and format**. Every user-facing and reference document in this directory follows its structure.

Key principles we adopt from 82079-1:
- §5.2 — **Identify the intended user** explicitly (a "Scope & Audience" block is mandatory in every document)
- §5.4 — **Hierarchical structure** with clear navigation aids (long documents must include a Table of Contents)
- §6.2 — **Information must be unambiguous, complete, and verifiable**
- §6.3 — **One topic per section; sections in logical reading order**
- §6.6 — **Navigation aids** (TOC, headings, links) must be present
- §7 — **Maintenance process** — every document has a documented review cadence and changelog

### ISO/IEC Directives, Part 2:2021 — Principles and rules for the structure and drafting of ISO and IEC documents

Defines the canonical structure for normative technical documents. The header block convention used in every Beetle Studio doc (`Project`, `Owner`, `Reviewers`, `ISO Standards`, `Version`, `Last Updated`) mirrors the ISO/IEC Directives front matter, and the body structure (Scope → Normative References → Terms → Overview → Body) is its standard.

### ISO/IEC 12207:2017 — Systems and software engineering — Software life cycle processes

The standard for software lifecycle processes. Every document in this directory is a **configuration item** under 12207 §6.2.5. Document maintenance, review, and approval are 12207 processes.

### Diátaxis documentation framework

A widely-adopted framework that categorizes documentation into four forms based on user need:
- **Tutorials** — learning-oriented (Quick Start)
- **How-to guides** — task-oriented (Troubleshooting, Launch Playbook, Beta Program Guide)
- **Reference** — information-oriented (Format Support Matrix, Keyboard Shortcuts, Component Library, Data Model, API Contract, VST SDK Integration, Effects Library, OpenFX Plugin SDK)
- **Explanation** — understanding-oriented (Architecture Overview, Technical Standards, Priority Framework, Roadmap, Changelog Policy)

Every document declares its Diátaxis form in its Scope & Audience block.

---

## Document Hierarchy

Documents are organized by **domain** (what the document is about) and **owner** (who is responsible). The directory tree:

```
docs/
├── README.md                       ← master index
├── STYLE_GUIDE.md                  ← this file
├── releases/                       ← distribution & versioning
├── engineering/                    ← development process & architecture
├── graphics/                       ← rendering & shader systems
├── codecs/                         ← format support
├── effects/                        ← effect engine & OpenFX SDK
├── timeline/                       ← timeline data model
├── audio/                          ← VST & audio systems
├── ui/                             ← UI component library
├── backend/                        ← API contracts
├── user/                           ← end-user documentation
├── help/                           ← FAQ & troubleshooting
├── product/                        ← roadmap & priority framework
├── operations/                     ← onboarding & infrastructure
├── community/                      ← community management
├── marketing/                      ← launch playbook
├── business/                       ← enterprise licensing
├── *.md                            ← cross-functional docs at root
```

Cross-functional documents (those with multiple owners from different domains) live at the `docs/` root and are listed in `README.md` under "Cross-Functional". This keeps each file's owner unambiguous.

---

## Filename Conventions

| Rule | Example | Notes |
|---|---|---|
| All uppercase with underscores | `OPENFX_PLUGIN_SDK.md` | Matches the existing project convention |
| `.md` extension only | `USER_GUIDE.md` | No `.markdown`, no `.txt` |
| No version numbers in filename | `USER_GUIDE.md` not `USER_GUIDE_v2.md` | Versions go in the header block |
| No author names in filename | `BUILD_SYSTEM.md` not `MIKE_BUILD.md` | Authors go in the header block |
| Topical prefix when natural | `OPENFX_PLUGIN_GUIDE.md`, `OPENFX_PLUGIN_SDK.md` | Distinguishes user-facing and dev-facing plugin docs |

Exceptions:
- `README.md` — lowercase, project index
- `STYLE_GUIDE.md` — lowercase + uppercase split, distinguishes the meta-document

---

## Document Header Block

Every document begins with this exact front matter block, in this order:

```markdown
# [Document Title]

**Project:** Beetle Studio
**Owner:** [Name] ([Role]) — [sub-area if multiple owners]
**Reviewers:** [Name] ([Role]), [Name] ([Role])
**ISO Standards:** [ISO/IEC 12207:2017 (area)], [ISO/IEC 25010:2023 (characteristic)]
**Version:** [SemVer, e.g. 1.0.0]
**Last Updated:** [Month YYYY]

---

## Overview

[2-4 sentence introduction. First sentence states what the document covers. Subsequent
sentences connect the document's content to specific ISO clauses or quality
characteristics, naming them explicitly.]

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | [what this document covers; one sentence] |
| **Diátaxis form** | [Tutorial / How-to / Reference / Explanation] |
| **Primary audience** | [who reads this] |
| **Secondary audience** | [who else might read it, if any] |

---

[Body of document...]

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | [Author] | Initial version |

### Review Cadence

- **Next review:** [date or trigger]
- **Reviewer:** [Name]
- **Cadence:** [Quarterly / Per release / On change / etc.]
```

### Header Block Field Reference

| Field | Required | Format | Example |
|---|---|---|---|
| `Project` | Yes | Fixed string | `Beetle Studio` |
| `Owner` | Yes | `Name (Role)` or `Name (Role) — sub-area` | `Sarah Miller (Build & Release Engineer)` |
| `Reviewers` | Yes | Comma-separated `Name (Role)` | `Kirk Beka (CTO), Mike Johnson (DevOps)` |
| `ISO Standards` | Yes | Comma-separated `ISO/IEC XXX:YYYY (area)` | `ISO/IEC 12207:2017 (lifecycle)` |
| `Version` | Yes | SemVer | `1.0.0` |
| `Last Updated` | Yes | `Month YYYY` | `June 2026` |

### ISO Standards Field Rules

- List the **specific ISO clause or sub-clause** in parentheses when the document maps to a known area (e.g. `ISO/IEC 12207:2017 §6.1.3 (system design)`)
- List the **specific quality characteristic** for ISO/IEC 25010:2023 (e.g. `usability`, `functional suitability`, `performance efficiency`, `maintainability`, `compatibility`, `security`, `reliability`, `portability`)
- Use **ISO 9241** (no year — it's a multi-part standard) for ergonomics and human-centered design
- For ISO/IEC 27001:2022, list the **Annex A control category** (e.g. `Annex A.8 (asset management)`, `Annex A.10 (cryptography)`)
- For ISO/IEC/IEEE 82079-1:2019, this guide itself is the canonical reference; other docs cite it only if they're directly about user-facing information design

---

## Body Structure

### Section Ordering

Sections within a document should follow this order (skip sections that don't apply):

1. **Overview** — required; 2-4 sentences; cites ISO clauses
2. **Scope & Audience** — required; defines who reads this and why
3. **Definitions / Glossary** — required if the document introduces 3+ domain terms
4. **Body** — the actual content
5. **References** — required; lists all linked docs and external standards
6. **Document Maintenance** — required; change log + review cadence

### Section Headings

- H1 (`#`) — used once for the document title
- H2 (`##`) — major sections (Overview, Scope, body sections, References, Maintenance)
- H3 (`###`) — subsections
- H4 (`####`) and deeper — use sparingly; prefer H3 with sub-bullets

### Table of Contents (Long Documents)

Documents ≥150 lines must include a Table of Contents after the Scope & Audience block:

```markdown
## Contents

- [Section A](#section-a)
- [Section B](#section-b)
  - [Subsection B.1](#subsection-b1)
- [Section C](#section-c)
- [References](#references)
- [Document Maintenance](#document-maintenance)
```

Use lowercase kebab-case in anchors. GitHub-flavored Markdown auto-generates anchors from heading text; if a heading has special characters, simplify the link text to match the auto-generated anchor.

### Prose Style

- **Use second person ("you") for user-facing docs, third person for engineering specs**
  - User-facing: "Drag the clip to the timeline."
  - Engineering: "The build system compiles each module to a separate static library."
- **Present tense for current state ("The pipeline uses..."), past tense for completed actions ("The PR was merged on...")**
- **Active voice over passive voice** — "The QA Lead runs benchmarks" not "Benchmarks are run by the QA Lead"
- **Avoid weasel words** — "very", "really", "just", "simply", "obviously"
- **Spell out acronyms on first use** — "DirectX 12 (DX12)", "Virtual Studio Technology (VST)"
- **Use SI units** — `2 GB` not `2 gigabytes`, `1080p / 30 fps` not `1080p 30fps`
- **Code in fenced code blocks** with language hints — ` ```cpp `, ` ```bash `, ` ```xml `
- **File paths in backticks** — `docs/releases/RELEASE_CHECKLIST.md`
- **UI elements in bold** — Click **File → Open Project**

### Tables

- Use tables for **structured comparison** (e.g. "Approach A vs Approach B", "Codec support matrix", "Shortcut reference")
- Don't use tables for **sequential steps** — use numbered lists
- Always include a header row
- Use `---` (not `===`) for alignment markers
- Right-align numerics, left-align text

### Lists

- **Numbered lists** for sequential steps
- **Bulleted lists** for unordered items
- **Checkboxes (`- [ ]`)** for action items / release gates
- **Nested lists** are allowed but flatten when depth exceeds 2

### Code Blocks

- **Always specify the language** — ` ```bash `, ` ```cpp `, ` ```json `, ` ```xml `, ` ```yaml `
- **Don't paste large code blocks into docs** — link to source files instead
- **Use code blocks for file contents, config samples, API examples, command sequences**

### Links

- **Use relative paths** for internal links — `../releases/RELEASE_CHECKLIST.md`
- **Use full URLs** for external links — `https://www.iso.org/standard/87206.html`
- **Markdown auto-links** (`<https://...>`) are forbidden — they render as raw URLs in many tools

### Diagrams

- **Use ASCII art in fenced code blocks** (no language hint) for simple diagrams
- For complex architecture diagrams, link to an external source (Mermaid, Draw.io) and keep the Markdown doc focused on text
- Always caption the diagram with a one-line description

---

## Tone & Voice

Beetle Studio documentation is **professional, precise, and direct**. We explain complex things clearly without dumbing them down.

- **Professional** — no slang, no jokes in the body, no emoji (except in release notes when explicitly relevant)
- **Precise** — use exact numbers, exact filenames, exact version numbers; no "and so on", no "etc." in technical content
- **Direct** — say what you mean in the fewest words; cut filler
- **Inclusive** — avoid gendered language ("the developer should... he" → "the developer should... they" or restructure)

---

## Maintenance Process

Per **ISO/IEC 12207:2017 §6.2.5 (Configuration Management)** and **ISO/IEC 14764:2022 (Software Maintenance)**:

1. **Every document has an owner** who is responsible for its accuracy.
2. **Every document has a review cadence** declared in its maintenance block.
3. **Every change increments the version** following [`releases/VERSIONING_POLICY.md`](releases/VERSIONING_POLICY.md):
   - **Major** (X.0.0) — material restructuring or scope change
   - **Minor** (0.X.0) — new content, new sections, new owners
   - **Patch** (0.0.X) — typo fixes, link updates, clarifications
4. **Every change is logged** in the document's Change Log table.
5. **PRs that change documentation must**:
   - Update the document's `Version` and `Last Updated` fields
   - Add a row to the document's Change Log
   - Be reviewed by the document's owner (or their delegate)
6. **Annual review** — every document is reviewed at least once per year, even if no changes were needed, and the Change Log records the review with version bump to the next patch.

### Review Cadence Defaults

| Document Type | Default Cadence |
|---|---|
| Release process docs | Every release cycle |
| Engineering standards | Quarterly |
| User-facing docs (User Guide, FAQ, Keyboard Shortcuts) | Monthly |
| Architecture / design docs | On subsystem change |
| Roadmap / Priority Framework | Quarterly |
| Compliance / security docs | Quarterly |
| Marketing / launch docs | Per campaign |
| Cross-functional docs | Quarterly |

Owners may set a stricter cadence in their document's maintenance block.

---

## References

### ISO Standards Cited in this Guide

| Standard | Used For |
|---|---|
| ISO/IEC/IEEE 82079-1:2019 | Information for use — content, structure, navigation, audience |
| ISO/IEC Directives Part 2:2021 | Document structure, front matter, normative sections |
| ISO/IEC 12207:2017 | Software lifecycle, configuration management, document as CI |
| ISO/IEC 14764:2022 | Maintenance process, change documentation |
| ISO/IEC 19770-2:2015 | Software identification (SWID tags) — see `releases/SWID_TAG_SPEC.md` |
| ISO/IEC 25010:2023 | Product quality model — characteristics cited in every doc |
| ISO/IEC 27001:2022 | Information security management — see `SECURITY_POLICY.md` |
| ISO/IEC 27002:2022 | Information security controls (Annex A) — see `SECURITY_POLICY.md` |
| ISO/IEC 27034-1:2011 | Application security framework — see `SECURITY_POLICY.md` |
| OWASP ASVS 4.0.3 | Application Security Verification Standard — see `SECURITY_POLICY.md` |
| OWASP Top 10 2021 | Most common web app risks — mapped to ASVS + Cloudflare WAF + Firebase rules |
| NIST SP 800-218 (SSDF 1.1) | Secure Software Development Framework — PR template practice tags |
| CWE Top 25 (2023) | Most dangerous software weaknesses — gated by Semgrep + SonarQube |
| WCAG 2.1 AA | Web accessibility — see `ACCESSIBILITY_COMPLIANCE.md` -> Website Design Testing |
| Core Web Vitals (LCP, CLS, INP) | Web performance — see `PERFORMANCE_BENCHMARKS.md` -> Web Performance |
| ISO 9241 (multi-part) | Ergonomics, human-centered design — see `ACCESSIBILITY_COMPLIANCE.md` |

### External Frameworks

- [Diátaxis](https://diataxis.fr/) — documentation structure framework
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — changelog format, see `releases/CHANGELOG_POLICY.md`
- [Semantic Versioning 2.0.0](https://semver.org/) — version numbering, see `releases/VERSIONING_POLICY.md`

### Related Internal Documents

- [`README.md`](README.md) — master index of all docs
- [`releases/VERSIONING_POLICY.md`](releases/VERSIONING_POLICY.md) — document versioning rules
- [`releases/CHANGELOG_POLICY.md`](releases/CHANGELOG_POLICY.md) — changelog format and authorship

---

## Document Maintenance

### Change Log

| Version | Date | Author | Change |
|---|---|---|---|
| 1.0.0 | June 2026 | Tom Anderson | Initial style guide. Codifies the conventions already followed by all 41 docs. Adds Scope & Audience block, Table of Contents rule for long docs, and explicit ISO/IEC/IEEE 82079-1:2019 reference. |

### Review Cadence

- **Next review:** June 2027
- **Reviewer:** Tom Anderson (Technical Writer), Kirk Beka (CTO)
- **Cadence:** Annual, or on adoption of a new ISO standard that affects documentation

---

*Grounded in ISO/IEC/IEEE 82079-1:2019, ISO/IEC Directives Part 2:2021, ISO/IEC 12207:2017, ISO/IEC 14764:2022, ISO/IEC 25010:2023, ISO/IEC 27001:2022, ISO/IEC 27002:2022, ISO/IEC 27034-1:2011, OWASP ASVS 4.0.3, OWASP Top 10 2021, NIST SP 800-218 (SSDF), CWE Top 25, Diátaxis.*
