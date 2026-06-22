> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `Auto Assign.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/AUTO_ASSIGN.md` in the docs repo.

---
title: "auto-assign.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "mike.johnson (DevOps Lead)"
status: "approved"
iso-refs: ["ISO/IEC 12207:2017 §6.3.5", "ISO/IEC 25010:2023 (Maintainability)"]
related-workflow: ".forgejo/workflows/auto-assign.yml"
---

# auto-assign.yml — Auto-assign Issues by Role

**Project:** Beetle Studio
**Owner:** Mike Johnson (DevOps Lead) — automation; Tom Anderson (Technical Writer) — role map
**Reviewers:** Kirk Beka (CTO), Amanda Clark (Operations Manager — org chart)
**ISO Standards:** ISO/IEC 12207:2017 §6.3.5 (Project process), ISO/IEC 25010:2023 (Maintainability)
**Forgejo Actions version:** Compatible with GitHub Actions syntax per [Forgejo Actions reference](https://forgejo.org/docs/latest/user/actions/reference/)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/auto-assign.yml` (8,512 bytes, 1 job)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Issue auto-assignment by role keyword matching, run on every issue open event |
| **Diátaxis form** | Reference |
| **Primary audience** | Mike Johnson (DevOps), all engineering leads |
| **Secondary audience** | New maintainers; future operators of the team roster |

---

## Purpose

This workflow eliminates manual triage of new issues. When a contributor opens an issue, the workflow inspects the title and body, runs a set of keyword matchers against a role → user map, and PATCHes the issue with the set of matching assignees via the Forgejo API.

The goal is to route work to the right owner within ~30 seconds of issue creation, with zero human action.

## Trigger

| Event | Types | Filter |
|---|---|---|
| `issues` | `opened` | none (fires for every new issue) |

- **No path filter** — runs on every issue open regardless of label or file touched.
- **No concurrency group** — duplicate runs on the same issue are unlikely because `opened` only fires once per issue; manual re-runs are uncommon.

## Jobs & Steps

### `auto-assign` (single job)

| Step | Purpose | Notes |
|---|---|---|
| 1. Install curl | Pre-flight on the runner; installs `curl` if missing | The default Forgejo Runner image is Debian bookworm with only Node.js pre-installed; curl is not always present |
| 2. Assign by team role | Read title + body, run 20 keyword matchers, build JSON, PATCH the issue | Uses `secrets.ADMIN_TOKEN`; calls `http://host.docker.internal:3000/api/v1` (host networking) |

#### Role Map (read from the workflow, authoritative)

The workflow encodes 20 keyword groups. Each group maps to one user. Keyword sets were assembled from the org chart in `docs/BEETLE_STUDIO_TEAM.md`. Excerpt:

| Assignee | Role | Sample keyword triggers |
|---|---|---|
| `mooned` | CEO / Lead Graphics Engineer | "core engine", "graphics engine", "vulkan render", "directx render", "cuda", "opencl", "simd", "memory manage", "gpu render", "rendering engine" |
| `kirk.beka` | CTO | "architect", "cross-platform", "security", "licens", "code review", "infrastructure", "org chart", "reporting line", "c++", "technical standard", "code standard", "system design" |
| `alex.chen` | UI/UX Lead | "qt6", "qml", "panel", "interface", "accessibility", "widget", "toolbar", "menu-bar", "dark-mode", "theme", "ui-framework", "ui-component", "dpi-scal", "docking", "winappdriver", "ui-test", "ui-bug", "ui-design", "ui/ux" |
| `maya.rodriguez` | Backend Lead | "firebase", "cloud func", "authenticat", "api endpoint", "database", "firestore", "sync", "backend", "server-side", "rest-api", "oauth", "sso", "cloud-sync", "waiver", "security-policy" |
| `james.park` | Graphics Engineer | "directx", "dx12", "vulkan", "shader", "hlsl", "glsl", "hdr", "lut", "color-manage", "preview-viewport", "gpu-profil", "renderdoc", "render-pipeline", "gpu-memory", "color-space", "color-science" |
| `sophie.williams` | Codec Engineer | "ffmpeg", "codec", "encod", "decod", "h.264", "h264", "hevc", "h.265", "av1", "prores", "nvenc", "quicksync", "transcode", "mux", "demux", "container-format", "frame-accurat", "scrub", "video-format", "bitrate", "pixel-format" |
| `daniel.kim` | Effects & Compositing Engineer | "effect", "composit", "color-correct", "color-grad", "blur", "sharpen", "noise-reduc", "openfx", "plugin-sdk", "lut-apply", "layer-blend", "keying", "chroma-key", "vignette", "grain", "mask", "rotoscop" |
| `emma.thompson` | Timeline Engineer | "timeline", "clip-trim", "split-clip", "undo", "redo", "multi-track", "ripple", "razor", "playhead", "marker", "nest-sequence", "keyboard-shortcut", "edit-point", "slip", "slide", "sequence", "track-lock" |
| `ryan.foster` | Audio Engineer | "audio", "sound-design", "mix-down", "equaliz", "compressor", "reverb", "vst-plugin", "waveform", "asio", "wasapi", "loudness", "meter", "fade-in", "fade-out", "sample-rate", "audio-sync", "audio-latency" |
| `lisa.martinez` | QA Lead | "test-suite", "test-case", "test-plan", "qa ", "bug-report", "regression", "benchmark", "beta-test", "quality-assur", "smoke-test", "automat-test", "flaky", "crash-report", "test-coverage", "test-strateg" |
| `chris.taylor` | Product Manager | "roadmap", "feature-request", "sprint", "user-research", "competitor", "product-manage", "backlog", "priorit", "user-stor", "requirement", "milestone", "schedule", "project-plan", "release-plan", "scope" |
| `nina.patel` | UX Designer | "wireframe", "prototype", "user-flow", "design-system", "figma", "mockup", "usability", "ux-design", "interaction-design", "layout-design", "user-journey", "persona", "heuristic" |
| `david.lee` | Motion Graphics Designer | "title-template", "motion-graphic", "transition-effect", "animation-preset", "default-template", "lower-third", "intro-template", "outro", "motion-design", "text-anim" |
| `mike.johnson` | DevOps Engineer | "ci/cd", "ci-cd", "pipeline", "docker", "azure", "deploy", "monitor", "alert", "github-action", "forgejo-action", "runner", "container", "devops", "cloudflare", "dns", "ssl", "cert-renew", "uptime", "incident", "disaster", "business-continu", "backup", "ci-alert", "slack-channel" |
| `sarah.miller` | Build & Release Engineer | "installer", "build-system", "packag", "code-sign", "windows-store", "msix", "inno-setup", "wix", "release-build", "version-bump", "cmake", "certificate-expir", "signing-cert", "store-submission", "artifact" |
| `jason.wong` | Marketing Manager | "marketing", "seo", "social-media", "press-release", "brand", "campaign", "newsletter", "advertis", "content-market", "analytics", "landing-page", "launch-event" |
| `rachel.green` | Community Manager | "community", "discord", "forum", "user-feedback", "support-ticket", "beta-program", "advocate", "tutorial-request", "moderati", "community-event" |
| `tom.anderson` | Technical Writer | "document", "tutorial", "help-center", "knowledge-base", "user-guide", "api-doc", "changelog", "release-note", "readme", "tech-writ", "troubleshoot", "style-guide", "doc-review", "doc-update", "onboarding-guide" |
| `amanda.clark` | Operations Manager | "recruit", "vendor", "legal", "contract", "finance", "onboard", "compliance", "office", "hiring", "payroll", "org-chart", "reporting-line", "team-structure", "employee", "benefits", "policy-manual", "operations" |
| `kevin.brown` | Business Development | "partner", "oem", "enterprise-sales", "licensing-deal", "marketplace", "business-develop", "revenue", "pricing", "subscription", "monetiz", "bundle", "reseller", "wholesale" |

> **Note:** The role list is hard-coded in the workflow. When team composition changes, both `auto-assign.yml` and `docs/BEETLE_STUDIO_TEAM.md` must be updated in lock-step.

## Configuration

### Required secrets

| Secret | Used for | Where set |
|---|---|---|
| `secrets.ADMIN_TOKEN` | Bearer token with `repo` + `write:issue` scope, calls `PATCH /api/v1/repos/{owner}/{repo}/issues/{N}` | Forgejo repo Settings → Secrets → Actions |

### Environment variables used

| Variable | Source | Purpose |
|---|---|---|
| `ISSUE_TITLE` | `${{ github.event.issue.title }}` | The raw issue title |
| `ISSUE_BODY` | `${{ github.event.issue.body }}` | The raw issue body |
| `ISSUE_NUM` | `${{ github.event.issue.number }}` | The issue number to PATCH |
| `REPO` | `${{ github.repository }}` | "beetle-studio/beetle-studio" |
| `API_TOKEN` | `${{ secrets.ADMIN_TOKEN }}` | Bearer for the PATCH call |
| `API_URL` | hard-coded `http://host.docker.internal:3000/api/v1` | Forgejo host reachable from runner container |

### Hard-coded assumptions

- The runner is configured with `host.docker.internal` reachable (Docker Desktop / DinD setup, not rootless Podman default).
- The Forgejo instance lives at `host.docker.internal:3000` (i.e., the host that runs the runner also runs Forgejo).
- The role → user list is stable. There is no current external roster file — it lives only in the workflow.

## Known Limitations

- **Greedy keyword matching can double-assign.** The `add()` helper deduplicates, but the script does not enforce a single assignee per issue. Multi-assignee is sometimes intentional (graphics-engineer + cto for security patches) but is noisy.
- **Lowercase only.** All matching is case-folded to lowercase. An issue titled "Add H.264 export" matches "h.264"; an issue titled "H.264" alone might miss because the pattern requires the dot. Verify by reading the workflow.
- **No negative matches.** A bug titled "Don't add OpenFX support" would still match `openfx` and assign `daniel.kim`.
- **No ML / LLM fallback.** If no keywords match, the issue is left unassigned. A future improvement: add a default assignee (e.g., `chris.taylor` for product/PM discussions) so that every issue has a human owner.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Issue is opened but no one is assigned | Body is empty, or none of the 20 keyword groups matched | Open the Actions log for the run; check whether the body parsing yielded text |
| Issue is double-assigned to overlapping roles | Two keyword groups matched (e.g., `ui-bug` matched `alex.chen` and the title also contained `test`) | Refine the keyword set; consider per-assignee exclusivity rules |
| Workflow fails with 401 | `secrets.ADMIN_TOKEN` is missing or expired | Regenerate the token; update the secret |
| Workflow fails with 404 from PATCH | The runner's `host.docker.internal` is not reachable from the container | Check the runner's network mode; on Linux DinD, may need `--add-host=host.docker.internal:host-gateway` |

## Adding a New Role

1. Add the user to the Forgejo organization with the right permissions.
2. Append a new keyword block to `auto-assign.yml` matching the `add "username"` pattern.
3. Mirror the new role in `docs/BEETLE_STUDIO_TEAM.md`.
4. Open a PR; the `Branch Naming` workflow will validate the branch name; the security and lint workflows are skipped because the path is `.forgejo/workflows/`, not `src/**`.
5. Merge → next opened issue will use the updated map.

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Branch Naming Workflow](./BRANCH_NAMING.md)
- [Branching Strategy](../BRANCHING_STRATEGY.md)
- [Beetle Studio Team Roster](../../../BEETLE_STUDIO_TEAM.md)
- [Operations Manual — Onboarding](../../../operations/ONBOARDING_GUIDE.md)

### External

- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/
- Forgejo Actions vs GitHub Actions — https://forgejo.org/docs/latest/user/actions/github-actions/ (note: `permissions` and `continue-on-error` job-level keys are ignored; OIDC uses `enable-openid-connect`)
- GitHub Actions expressions — https://docs.github.com/en/actions/learn-github-actions/expressions
- ISO/IEC 12207:2017 §6.3.5 — Project process (work assignment)
- ISO/IEC 25010:2023 — Maintainability subcharacteristic

---

*Grounded in: ISO/IEC 12207:2017 §6.3.5 (Project process), ISO/IEC 25010:2023 (Maintainability). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/auto-assign.yml`.*
