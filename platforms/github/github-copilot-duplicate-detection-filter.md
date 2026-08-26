# GitHub Copilot Duplicate Detection Filter

## Overview
The duplicate detection filter (also referenced in GitHub/Microsoft security-
controls documentation as "public-code filter") is a guardrail that blocks or
flags Copilot suggestions that closely match publicly available code. When
enabled, a completion or chat suggestion that would reproduce a meaningful
chunk of public source is suppressed (or, depending on the mode, surfaced with
a warning) instead of being offered verbatim. It is the primary technical
control behind the Copilot Copyright Commitment
(`github-copilot-copyright-commitment.md`).

## Symptom
- An engineer reports Copilot "stopped giving me the good completions" —
  specifically, longer multi-line completions that previously matched common
  OSS patterns no longer appear. This is the filter working, not a regression.
- A code review surfaces a function that looks verbatim copied from a popular
  Apache-2.0 library, but the engineer insists they used Copilot. The filter
  may have been disabled for that user/org, or the match fell below the
  threshold.
- Legal asks "how do we know Copilot is not just pasting LGPL code into our
  closed-source product?" — the answer is the duplicate detection filter, and
  you need to confirm it is enforced, not merely available.
- License-scanning tools (e.g., `licensefinder`, ScanCode) flag Copilot-
  generated files with surprising license matches; the filter's threshold is
  probabilistic, not absolute.

## Gotchas
- **Off by default in some surfaces, on in others.** Historically the filter
  has been "on" when the user opts into the public-code match-blocking and
  "off" otherwise, and the default has changed across releases. Confirm the
  *current* policy at the org level rather than relying on memory.
- **Filter is a match probability, not a cryptographic check.** It will not
  catch paraphrased code, renamed identifiers, or small snippets that are
  individually unoriginal but collectively copied. It is a coarse filter, not
  a clean-room guarantee.
- **Threshold tuning trades precision for recall.** A strict setting rejects
  many false positives (boilerplate, idiomatic patterns) and frustrates
  engineers; a loose setting lets more through. Most orgs should use the
  recommended default and resist tuning without data.
- **Chat and inline completion behave differently.** The filter historically
  applied to inline completions; chat answers that reproduce public code may
  be governed by a different code path. Verify coverage for the surfaces your
  engineers actually use (IDE, web chat, CLI, coding agent).
- **Disabled via user setting is easy to miss.** Even if the org policy says
  "on", individual users on Copilot Individual subscriptions or with org
  overrides can turn the filter off locally. Centrally enforce it.
- **Custom-model / fine-tuned setups.** If your enterprise uses a custom
  Copilot model endpoint, confirm the filter still applies. Some custom
  routing bypasses the public-code filter pipeline.
- **Filter does not catch your own private code.** If your monorepo contains
  code under multiple licenses (e.g., an MPL-2.0 module inside a proprietary
  product), the filter does not protect against internal copying because it
  only checks against the public-code index.

## Enabling and Verifying
- **Org policy (Copilot Enterprise/Business):** Settings > Copilot > Policies
  > "Suggestions matching public code" → set to Block (or Allow-with-warning
  during a rollout).
- **Verify per-user:** the user-side setting lives in their Copilot
  preferences; an org-wide block policy should override it. Document the
  override behavior for your edition.
- **Evidence for Legal:** capture a screenshot of the org policy and a date,
  and re-capture whenever GitHub changes defaults. This is the artifact the
  Copilot Copyright Commitment conditions on.

## What It Does Not Do
- It does not assert the suggested code is *license-clean*. A short snippet
  that passes the filter can still be subject to attribution requirements
  under an OSS license.
- It does not catch generated code that is functionally identical but
  syntactically rearranged.
- It does not provide an audit trail of what was blocked unless you enable
  Copilot telemetry/audit logging alongside it
  (`github-copilot-cli-usage-metrics.md`, `github-audit-log-api.md`).
- It does not protect against the engineer pasting public code into the
  editor manually (i.e., without Copilot). It only governs Copilot output.

## Operational Pattern
1. Set the org policy to Block matching public code.
2. Run a 30-day "warn" mode to identify which teams hit the filter most and
   why; usually this is genuine OSS boilerplate and not a real risk.
3. Flip to Block. Communicate to engineers that longer completions may be
   shorter than before — this is expected.
4. Pair with a periodic license scan of the repo (the filter catches
   Copilot-originated matches; license scan catches everything else).
5. Re-verify the policy after every Copilot feature release; defaults shift.

## Adjacent Controls
- **Copilot Copyright Commitment** — the legal backstop that conditions on
  this filter being enabled.
- **Secret scanning + push protection** (`github-secret-scanning.md`) —
  different threat (secrets leaving the repo) but part of the same "what is
  in our code" hygiene story.
- **Dependency review** (`github-dependency-review.md`) — covers imported
  code; duplicate-detection covers generated code.

## Summary
The duplicate detection filter is the single most important Copilot control
for any org shipping closed-source software. Enable it at the org level,
enforce it centrally, keep evidence that it is on, and never let "engineers
find it annoying" be the reason it gets disabled — that is also the reason the
Copyright Commitment stops applying.
