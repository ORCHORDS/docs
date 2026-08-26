# iframe-sandboxing-untrusted-embeds

**Issue:** The app embeds content it does not fully control — user-generated HTML previews, third-party widgets, ad frames, file previews, payment iframes. Rendered unsandboxed, that content runs with its origin's full power: script execution, plugin loading, top-level navigation away from your app, and (if same-origin) direct access to your DOM and cookies via `parent`. The `sandbox` attribute is the browser-enforced least-privilege mechanism for this direction of framing — distinct from clickjacking defense (`X-Frame-Options`/CSP `frame-ancestors`), which protects *your* page from being framed by others. Both directions are needed; they solve different problems.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Sandbox token model

1. **A bare `sandbox` attribute applies maximum restrictions.** `sandbox` or `sandbox=""` blocks scripts, forms, popups, top navigation, and treats the content as a unique opaque origin; you then re-enable only the capabilities the embedded content genuinely needs.
2. **Every token is a privilege grant, so add sparingly.** `allow-scripts`, `allow-forms`, `allow-popups`, `allow-modals`, `allow-downloads`, `allow-pointer-lock`, `allow-top-navigation*` each reopen a specific attack channel — the review question for each is "what breaks without it," not "what might need it."
3. **Without `allow-same-origin`, the frame gets a unique opaque origin.** It cannot read its own cookies/storage from its real origin nor reach the embedder's — this is the isolation property that makes sandboxing user HTML previews safe; keep it absent unless the content is genuinely yours.
4. **Never combine `allow-scripts` and `allow-same-origin` for same-origin content.** MDN's warning is explicit: a scripted, same-origin frame can reach into the parent DOM and *remove its own sandbox attribute*, making the sandbox worthless. This combination must be treated as a finding by any security review.
5. **Top-navigation tokens deserve special caution.** `allow-top-navigation` lets the frame redirect your whole tab (classic ad-redirect abuse); prefer `allow-top-navigation-by-user-activation` so navigation requires a user gesture, or none at all.
6. **Sandbox flags inherit into popups.** Windows opened from a sandboxed frame inherit its restrictions (forms silently failing in popped-out windows is a known gotcha); `allow-popups-to-escape-sandbox` exists for legit escape hatches but reopens the excluded capabilities — review it like any other grant.

## Safe embedding patterns

1. **Render untrusted HTML via `srcdoc` with a bare `sandbox`.** For user-content previews, inline the HTML into a `<iframe sandbox srcdoc="...">` — no scripts run, no navigation escapes, no origin access; this is MDN's own pattern for exactly this case.
2. **Prefer `src` to a separate origin for full documents.** When embedding whole pages (previews, third-party apps), serve them from a dedicated domain so even a sandbox escape lands in an origin with no cookies worth stealing; sandboxing alone is defeated if the user can open the frame URL directly in a new tab.
3. **Add `csp` attribute for per-frame policy.** The iframe `csp` attribute applies a Content-Security-Policy to the embedded document on load (e.g., `csp="default-src 'none' script-src 'none'"`), layering a second ceiling under the sandbox.
4. **Wrap embeds with defense on the embedder side too.** Keep your page's own CSP `frame-src` restricted to the origins you actually embed, so an injected iframe pointing elsewhere never loads.
5. **Constrain sizing and interactions deliberately.** `referrerpolicy="no-referrer"` on the iframe prevents leaking your URLs into embedded third-party content; `loading="lazy"` and fixed dimensions prevent layout-based abuse of your viewport.
6. **Give every iframe a `title`.** Accessibility is part of safe embedding; screen-reader users must know what the frame contains ("Untrusted comment preview") to make sense of the isolated island.

## Pitfalls and review checklist

1. **Check every `sandbox` value in the codebase for dangerous token pairs.** Grep for `allow-scripts` + `allow-same-origin` co-occurrences and for `allow-top-navigation` without user-activation; both patterns should require a written justification comment.
2. **Remember the `error` event never fires on iframes.** Browsers suppress it as an anti-network-probing measure and `load` fires even on failure — do not build "failed safely?" logic on iframe error events, and do not treat a `load` as content-trust evidence.
3. **Do not confuse sandbox with authentication.** Sandboxed frames still make network requests; an embedded same-app page in a sandbox still executes with the user's session if you add `allow-same-origin` — sandbox is a capability fence, not an identity boundary.
4. **Watch for token creep across releases.** "Temporarily" added tokens to fix a widget outage tend to become permanent; diff sandbox attributes in code review like you would diff IAM policies.
5. **Test escape attempts directly.** In a sandboxed preview frame, attempt `top.location = ...`, form submission, `window.open`, cookie access, and `parent.document` access — each must be blocked by the configured token set.
6. **Pair with the framing-protection direction.** Your own pages still need `Content-Security-Policy: frame-ancestors 'none'` (or your allowed embedders) so the sandbox story is not one-sided; embedding others safely and being embedded safely are separate controls.

## Verification

1. **Unit-test the preview renderer** to assert generated frames always carry `sandbox` and never carry both dangerous tokens, regardless of user input content.
2. **Manually attempt top-navigation and popup escape** from a sandboxed embed containing attacker script; the browser must block both.
3. **Confirm opaque-origin isolation** — an embedded script attempting `document.cookie` or `localStorage` of its real origin must fail (SecurityError) when `allow-same-origin` is absent.
4. **Open the frame's URL directly in a new tab** and verify the separate-origin strategy contains what it should (no session cookies, inert headers).
5. **Audit with a CSP report-only pass** before enforcing `frame-src` restrictions, so legitimate embeds are enumerated before locking down.

**Source:** [MDN: `<iframe>`](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe), [MDN: sandbox attribute](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/sandbox).
