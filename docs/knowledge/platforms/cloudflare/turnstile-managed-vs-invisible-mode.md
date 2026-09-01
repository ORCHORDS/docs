# Turnstile Managed Versus Invisible Mode

Turnstile widgets come in more than one temperament. Managed mode asks the browser to run non-interactive challenges and shows a visible box only when the risk signal warrants it; non-interactive mode never shows UI but still runs challenges; invisible mode renders nothing at all and never interrupts the user, at the cost of weaker signals. Choosing between them is a trade between bot-resistance, accessibility, and conversion friction, and the right answer differs per surface: a login form tolerates an occasional checkbox far better than a one-tap mobile checkout. This article compares the modes and sets the decision rules.

## Scope

Covers Turnstile widget mode selection — managed, non-interactive, and invisible — including accessibility implications, user friction, and verification of that the chosen mode is actually behaving as expected. Applies to public-facing forms, login, signup, and checkout flows embedding Turnstile. Excludes server-side token verification details (mode choice does not change the siteverify contract), pre-clearance integrations, and Web Application Firewall rules.

## Workflow or implementation guidance

1. List the surfaces to be protected and rate each on three axes: abuse cost if bots pass (account creation spam versus payment fraud), user sensitivity to friction (anonymous browsing versus committed checkout), and accessibility requirements.
2. Default to managed mode for most surfaces. Managed adapts: most users see nothing intrusive, while risky sessions get a visible challenge, which concentrates friction where risk lives.
3. Reserve invisible mode for surfaces where any interruption is unacceptable, and accept the trade: invisible widgets provide fewer interaction signals, so filtering strength is lower than managed.
4. Consider non-interactive mode as the middle option — no UI by default but still running challenges — when you want stronger signals than invisible without managed's occasional visible challenge.
5. For accessibility, verify keyboard and screen reader behavior per mode: any mode that can render visible UI must remain operable without a pointer, and the widget markup must be announced correctly. Invisible mode avoids interaction demands entirely, which helps some users but is not a substitute for accessible fallbacks.
6. Implement per-surface configuration: each surface gets its own widget configuration with the mode chosen for it, rather than one shared setting for the whole site.
7. Measure after rollout: challenge-completion rates, abandonment at the protected step, and verified-token failure rates per surface, compared against the pre-Turnstile baseline.
8. Review mode choices quarterly against those numbers, and after any observed abuse campaign, upgrading a surface to managed or downgrading when friction dominates without abuse.

## Controls

- Per-surface mode registry: each protected surface records its mode and the rationale tied to the three-axis rating.
- Accessibility conformance check: any surface whose mode can show visible UI passes a keyboard-only and screen-reader test before release.
- Friction budget: each surface defines a maximum acceptable step abandonment increase attributable to the widget; exceeding it triggers mode review.
- Signal-strength expectation: invisible-mode surfaces carry a documented note that filtering strength is lower, so abuse metrics are watched more closely.
- Independent configuration: no shared widget configuration across surfaces with different friction or risk profiles.
- Quarterly mode review with metrics: completion rates, abandonment, and token verification outcomes per surface.

## Validation evidence

- The per-surface mode registry with rationale and review dates.
- Accessibility test records (keyboard navigation, screen reader announcement) for surfaces with visible-capable modes.
- Widget rendering verification: HTML embedding the correct site key and mode, confirmed on a deployed page rather than only in code review.
- Token verification log evidence showing tokens from each mode being validated server-side.
- Metrics comparison per surface: challenge completion, abandonment, and verification failures, before and after mode changes.
- Quarterly review notes recording keep/change decisions with the supporting metric.

## Failure modes and correction

- Invisible mode admits a bot wave: the signal deficit is structural; upgrade the surface to managed (or non-interactive as an intermediate) and monitor completion rates through the transition.
- Managed mode shows the visible challenge too often for a low-risk surface: review traffic quality and consider non-interactive for that surface, watching verification failure rates after the switch.
- Users with assistive technology blocked at the widget: the visible challenge path failed accessibility testing; fix focus handling and announcement, and provide a contact fallback while remediating.
- Widget never renders due to script blocking or misconfigured domain: verification failures spike; confirm the site's domain list includes the deployed origin and monitor render success rate.
- One global configuration shared across surfaces: split it so login and checkout can diverge; the registry control exists to catch this.
- Mode changed without re-measuring friction: revert to the previous mode until the measurement window completes, keeping decisions evidence-based.

## Limitations

- Invisible mode trades filtering strength for zero friction by design; it cannot be made as strong as managed.
- Managed mode's decision to show a visible challenge is adaptive and not operator-forced per request.
- Friction and completion metrics require analytics instrumentation on the protected step; without it, mode reviews run blind.
- Accessibility outcomes depend on surrounding page markup and assistive technology combinations that vary.
- Mode choice affects client behavior only; server-side token verification follows the same contract regardless of mode.

## Canonical sources

- Cloudflare Turnstile docs, "Turnstile widgets" (widget modes and behavior): https://developers.cloudflare.com/turnstile/concepts/widget/
- Cloudflare Turnstile docs, "Concepts": https://developers.cloudflare.com/turnstile/concepts/
