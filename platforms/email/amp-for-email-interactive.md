# amp-for-email-interactive

**Issue:** Product wants interactive email — forms, carousels, live-updating content, one-click actions inside the message — and the team must decide whether AMP for Email is worth building. The honest 2026 answer is that only a handful of clients render it (Gmail, Yahoo/AOL, Mail.ru, FairEmail), Google requires a sender registration and DKIM before dynamic email is accepted, and every AMP message still needs a complete HTML fallback because the majority of recipients (Outlook, Apple Mail, everything else) will never see the interactive part. Building it blind leads to rejected registrations, broken fallbacks, and interactive features that a majority of the list silently never receives.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Current support matrix (2026)

1. **Clients that render AMP: a short list.** Per the official amp.dev support page, AMP for Email renders in Gmail, Yahoo Mail, AOL Mail, Mail.ru, and FairEmail — Outlook.com announced support in 2019 and later backed out, and Apple Mail has never supported it, so those recipients always see the fallback part.
2. **Sender whitelisting is required per provider.** Gmail requires a registration/approval of the sending identity before dynamic email is delivered as interactive; Yahoo has its own sender approval process, meaning a single campaign can be interactive in Gmail and static in Yahoo until both approvals exist.
3. **Most major ESPs can transmit it.** AWS SES, SendGrid, Mailgun, SparkPost, Braze, Iterable, Klaviyo, Customer.io, and others appear on the amp.dev platform list, so the constraint is rarely the transport — it is client coverage and registration.
4. **Measure the reachable share before building.** If Gmail + Yahoo/AOL recipients are 40% of a B2B list that lives in Outlook, the interactive experience reaches far less than the headline client numbers suggest; decide with the actual domain breakdown of your list.
5. **Treat AMP as progressive enhancement.** The only sustainable architecture is HTML-first: the fallback must be a complete, fully usable email, with AMP as an upgrade for the subset of clients that accept it.

## MIME structure and fallbacks

1. **AMP rides in a dedicated MIME part.** A dynamic email is `multipart/alternative` containing `text/x-amp-html` placed *before* the `text/html` part (which itself precedes `text/plain`); AMP-capable clients pick the AMP part, everyone else picks HTML or plain text silently.
2. **The HTML part is the real email.** Every link, button, and piece of information in the AMP version must exist in the HTML fallback — clients that ignore the AMP part do so without any user-visible notice, so information that exists only in the AMP part is simply lost.
3. **Validate structure before sending.** The AMP Playground and the AMP validator (`amp-validator` npm package, `amp4email` transformer) catch malformed markup; Gmail additionally rejects dynamic email whose AMP part fails validation, which surfaces as the message delivering as plain HTML rather than an error to the sender.
4. **Watch multipart size limits.** Carrying three alternatives (AMP + HTML + plain text) inflates message size; keep the AMP part lean and prune duplicated assets, since Gmail clips large messages regardless of which part renders.
5. **Test the fallback with the same rigor as the AMP part.** Rendering checks across Outlook, Apple Mail, and dark-mode Gmail apply to the HTML part — the AMP work must not degrade the message the other half of the list receives.

## Gmail registration and requirements

1. **Build → test → register is the official sequence.** Google's developer docs (developers.google.com/gmail/ampemail) require building the email, testing it, and then registering the sender before dynamic email reaches recipients; production AMP cannot be sent cold.
2. **DKIM must be signing the mail.** Dynamic email must be DKIM-signed; a message without valid DKIM will not render its interactive part even after registration, so finish SPF/DKIM/DMARC work first.
3. **Self-test with `#ampemail=true`.** During development, sending the message to your own registered Gmail address with `#ampemail=true` appended to the subject forces Gmail to render the AMP part for inspection before any approval.
4. **Registration is per sending identity.** The approval covers the From: domain involved; adding a new sending domain or a new ESP means re-registration, so centralize which domains send AMP.
5. **Yahoo approval is a separate process.** Yahoo's sender hub (senders.yahooinc.com) has its own AMP sender requirements; being live in Gmail does not carry over.

## Runtime constraints and security model

1. **No arbitrary JavaScript, ever.** AMP for Email is safe precisely because it allows only the vetted AMP component set (`amp-img`, `amp-list`, `amp-form`, `amp-carousel`, `amp-bind`, etc.) with a strict CSP — custom scripts, external JS, and most CSS are stripped or rejected outright.
2. **Forms and actions hit your HTTPS endpoints.** `amp-form` submissions and `amp-list` refreshes are live requests to your servers at open/interaction time; those endpoints must be CORS-enabled, production-grade, and must not leak per-user data across recipients when the same email is fetched by different users.
3. **Dynamic content is server-refreshed, not frozen.** `amp-list` content is fetched when the client renders it, which is the feature (live data in email) and the trap — the message must still make sense when the endpoint returns empty, errors, or stale data.
4. **Treat interactive state as ephemeral.** Clients refresh, re-fetch, and eventually stop re-rendering dynamic parts; Gmail serves dynamic content for a limited period and older messages show the static fallback, so AMP must never be the only place a transaction's outcome is recorded.
5. **Every interactive action needs a non-AMP path.** A form usable only inside AMP excludes the majority of the list on day one; the durable pattern is a prominent link to the same action on the web app, with AMP as a convenience shortcut.

## When to use it, and alternatives

1. **Strongest fits: stateless interactions on fresh mail.** RSVP toggles, one-question polls, cart nudges, and catalog carousels sent to engaged Gmail-heavy consumer lists get real value; cold acquisition mail and B2B Outlook-heavy lists get almost none.
2. **CSS-only interactivity covers part of the gap.** The checkbox-hack and "ETK" (interactive toolkit) techniques from vendors like Mailmodo deliver accordion/carousel/tab behavior in plain HTML across a wider client set than AMP, without registration — with their own rendering quirks in Outlook.
3. **The web link is the universal fallback.** For anything transactional or stateful, the highest-reliability "interactive email" in 2026 is still a fast, authenticated deep link into your app; budget engineering time there before spending it on AMP registration.
4. **Instrument both parts separately.** Track AMP-part interactions and fallback-part clicks as distinct events, otherwise engagement numbers silently blend two different experiences and the AMP ROI case becomes unanswerable.
5. **Re-check the support matrix yearly.** The AMP email ecosystem has shifted before (Outlook withdrawing, provider list changes); re-verify against amp.dev and provider sender hubs before each major campaign season rather than relying on a stale internal doc like this one.
