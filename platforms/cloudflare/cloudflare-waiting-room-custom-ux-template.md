# Cloudflare Waiting Room Custom UX Template

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The default Cloudflare Waiting Room page is generic — plain Cloudflare branding
with an estimated wait time.  You need to match your brand identity, show a
progress bar instead of raw minutes, play a video or animation, let users
opt-in to email notifications, or display real-time updates without page
refreshes.  Cloudflare Waiting Room supports fully custom HTML/CSS/JS templates
that replace the default page entirely.

---

## Context

A Cloudflare Waiting Room queue page is served when traffic exceeds the
configured `total_active_users` or `session_duration` thresholds.  The custom
template feature (available on Business and Enterprise plans, and on Workers
Paid for programmatic creation) lets you replace the built-in HTML with your
own.

Template variables are injected server-side at render time using a
`{{variable}}` syntax (Mustache-compatible):

| Variable | Type | Description |
|---|---|---|
| `{{waitTime}}` | integer | Estimated wait in minutes (0 = less than 1 minute) |
| `{{waitTimeKnown}}` | boolean | `true` if estimate is available |
| `{{queueIsFull}}` | boolean | `true` when queue is at capacity |
| `{{queueAll}}` | boolean | `true` when room is in "Queue All" mode |
| `{{customData}}` | object | JSON object from the Additional Data field |
| `{{timeUntilEventStartsMinutes}}` | integer | For event-based rooms |
| `{{eventStartsAt}}` | string | ISO timestamp of event start |
| `{{refreshIntervalSeconds}}` | integer | How often the page auto-refreshes |

The page **auto-refreshes** at the `refreshIntervalSeconds` interval (30 s by
default).  JavaScript can suppress or augment this by intercepting the meta
refresh.

---

## Full Custom Template Example

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta http-equiv="refresh" content="{{refreshIntervalSeconds}}" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>We'll be right with you — Acme</title>
  <style>
    :root {
      --brand-primary: #2563eb;
      --brand-secondary: #1e40af;
      --surface: #f8fafc;
      --text: #0f172a;
      --muted: #64748b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: system-ui, -apple-system, sans-serif;
      background: var(--surface);
      color: var(--text);
      min-height: 100dvh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .card {
      background: white;
      border-radius: 1.5rem;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
      padding: 3rem 2.5rem;
      max-width: 480px;
      width: 100%;
      text-align: center;
    }
    .logo { margin-bottom: 2rem; }
    .logo img { height: 48px; }
    h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 0.5rem; }
    .subtitle { color: var(--muted); margin-bottom: 2rem; font-size: 0.95rem; }
    .wait-badge {
      background: var(--brand-primary);
      color: white;
      border-radius: 9999px;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 1.25rem;
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 1.5rem;
    }
    .progress-track {
      background: #e2e8f0;
      border-radius: 9999px;
      height: 8px;
      margin-bottom: 1.5rem;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--brand-primary), var(--brand-secondary));
      border-radius: 9999px;
      transition: width 0.6s ease;
    }
    .queue-full-notice {
      background: #fef3c7;
      border: 1px solid #fbbf24;
      border-radius: 0.75rem;
      padding: 0.75rem 1rem;
      font-size: 0.875rem;
      color: #92400e;
      margin-bottom: 1.5rem;
    }
    .timer {
      font-size: 0.8rem;
      color: var(--muted);
      margin-top: 1.5rem;
    }
    .email-form {
      display: flex;
      gap: 0.5rem;
      margin-top: 1.5rem;
    }
    .email-form input {
      flex: 1;
      border: 1px solid #cbd5e1;
      border-radius: 0.5rem;
      padding: 0.6rem 0.75rem;
      font-size: 0.9rem;
      outline: none;
    }
    .email-form input:focus { border-color: var(--brand-primary); }
    .email-form button {
      background: var(--brand-primary);
      color: white;
      border: none;
      border-radius: 0.5rem;
      padding: 0.6rem 1rem;
      cursor: pointer;
      font-size: 0.9rem;
    }
    .email-form button:disabled { opacity: 0.6; cursor: default; }
    .custom-message { color: var(--muted); font-size: 0.875rem; margin-top: 1rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">
      <!-- Replace with your own logo -->
      <svg width="120" height="32" viewBox="0 0 120 32" fill="none">
        <rect width="32" height="32" rx="8" fill="#2563eb"/>
        <text x="40" y="22" font-family="system-ui" font-size="16" font-weight="700" fill="#0f172a">Acme</text>
      </svg>
    </div>

    <h1>Just a moment…</h1>
    <p class="subtitle">High demand right now. Your spot is saved.</p>

    {{#queueIsFull}}
    <div class="queue-full-notice">
      The queue is currently full. Please check back shortly.
    </div>
    {{/queueIsFull}}

    {{#waitTimeKnown}}
    <div class="wait-badge">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 6v6l4 2"/>
      </svg>
      About <span id="wait-minutes">{{waitTime}}</span> min
    </div>

    <!-- Progress bar: 60 min max = 100%; adjust for your use case -->
    <div class="progress-track">
      <div
        class="progress-fill"
        id="progress-fill"
        style="width: {{waitTime}}%"
      ></div>
    </div>
    {{/waitTimeKnown}}

    {{^waitTimeKnown}}
    <div class="wait-badge">Estimating your wait…</div>
    {{/waitTimeKnown}}

    {{#customData.bannerMessage}}
    <p class="custom-message">{{customData.bannerMessage}}</p>
    {{/customData.bannerMessage}}

    <!-- Optional email notification opt-in -->
    <form class="email-form" id="notify-form">
      <input type="email" id="notify-email" placeholder="Get notified by email" />
      <button type="submit" id="notify-btn">Notify me</button>
    </form>

    <p class="timer" id="refresh-timer">
      Page refreshes in <span id="countdown">{{refreshIntervalSeconds}}</span>s
    </p>
  </div>

  <script>
    // ── Countdown timer ────────────────────────────────────────────────────
    const refreshSec = parseInt("{{refreshIntervalSeconds}}", 10) || 30;
    let remaining = refreshSec;
    const countdownEl = document.getElementById("countdown");

    const timer = setInterval(() => {
      remaining -= 1;
      if (countdownEl) countdownEl.textContent = String(remaining);
      if (remaining <= 0) clearInterval(timer);
    }, 1000);

    // ── Progress bar fill (cap at 60 min = 100%) ──────────────────────────
    const waitMin = parseInt("{{waitTime}}", 10) || 0;
    const fillEl = document.getElementById("progress-fill");
    if (fillEl && waitMin > 0) {
      const pct = Math.min(Math.round((waitMin / 60) * 100), 100);
      fillEl.style.width = pct + "%";
    }

    // ── Email notification opt-in ──────────────────────────────────────────
    const form = document.getElementById("notify-form");
    const btn  = document.getElementById("notify-btn");
    if (form && btn) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("notify-email").value;
        if (!email) return;
        btn.disabled = true;
        btn.textContent = "Saving…";
        try {
          // POST to your own notification Worker endpoint
          await fetch("https://notify.example.com/waiting-room-subscribe", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, url: location.href }),
          });
          btn.textContent = "✓ We'll notify you";
        } catch {
          btn.disabled = false;
          btn.textContent = "Retry";
        }
      });
    }
  </script>
</body>
</html>
```

---

## Uploading the Custom Template via API

```bash
ZONE_ID="your-zone-id"
TOKEN="your-api-token"
ROOM_ID="your-waiting-room-id"
TEMPLATE_FILE="waiting-room-template.html"

# Update an existing room with a custom page template
curl -sS -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${ROOM_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"custom_page_html\": $(jq -Rs . < "${TEMPLATE_FILE}")
  }" | jq '{name: .result.name, custom_page_enabled: (.result.custom_page_html != null)}'
```

---

## Injecting Dynamic Data via `customData`

The `Additional Data` field on the Waiting Room accepts a JSON object that is
available in the template as `{{customData.*}}`.  Use this for:

- Promotional messages or sale countdowns
- Queue-specific support links
- Event names or ticket tier labels

```bash
# Set customData on a room
curl -sS -X PATCH \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${ROOM_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "additional_routes": [],
    "json_response_enabled": false,
    "custom_json_response": null,
    "description": "Sale launch queue",
    "custom_page_html": null
  }' | jq .
```

The `customData` JSON is set in the dashboard under **Additional Data** or via
the `json_response_enabled` / `custom_json_response` API fields.

---

## Monitoring Waiting Room State from a Worker

For advanced scenarios — dynamically adjusting thresholds or retrieving live
queue depth — use the Waiting Room Status API from another Worker:

```typescript
export interface Env {
  CF_API_TOKEN: string;
  CF_ZONE_ID: string;
}

interface WaitingRoomStatus {
  status: "queueAll" | "queueing" | "notQueueing";
  estimatedQueuedUsers: number;
  maxEstimatedTimeMinutes: number;
  eventId: string | null;
}

export async function getWaitingRoomStatus(
  zoneId: string,
  roomId: string,
  token: string,
): Promise<WaitingRoomStatus> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${zoneId}/waiting_rooms/${roomId}/status`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  const { result } = (await res.json()) as { result: WaitingRoomStatus };
  return result;
}
```

---

## Anti-patterns

- **Blocking the meta refresh** — if your JavaScript prevents `<meta
  http-equiv="refresh">` from firing, users may stay in the queue indefinitely
  with a stale token.  Always let the auto-refresh run or implement a JS-based
  polling refresh that calls the same URL.
- **External CDN dependencies in the template** — the Waiting Room page is
  served under a Cloudflare-managed origin.  External CDN scripts (Google
  Fonts, React CDN) may fail during high-traffic events if those CDNs are also
  under load.  Inline all CSS and JS or use system fonts.
- **Using `{{waitTime}}` directly in a progress bar without capping** — wait
  times can exceed 60 or 120 minutes during large events.  Always cap the
  progress fill at 100% in JavaScript.
- **Exposing internal queue metrics in `customData`** — `customData` is
  rendered into the HTML sent to the browser.  Do not put internal counts,
  user IDs, or pricing logic there.
- **Template over 1 MB** — Cloudflare enforces a template size limit.  Inline
  images as tiny placeholders and load large assets (hero images, videos) from
  your own CDN after the page renders.

---

## Gotchas

- The `{{#waitTimeKnown}}` Mustache block only renders when Cloudflare has
  enough data to estimate the queue.  In the first few seconds of a traffic
  spike, `waitTimeKnown` is `false`.  Always provide a fallback `{{^waitTimeKnown}}`
  block.
- Custom templates must be valid HTML — unclosed tags or broken JavaScript can
  cause the Waiting Room page to fail silently.  Test with the Waiting Room
  **Preview** feature in the dashboard before deploying to production.
- The `refreshIntervalSeconds` variable reflects the room's configured refresh
  interval, but browsers may throttle the meta-refresh if the tab is in the
  background.  Do not rely on exact refresh timing for any business logic.
- Custom Waiting Room pages are **not** served through Pages or Workers — they
  are rendered by Cloudflare's Waiting Room infrastructure.  You cannot add
  Workers bindings (KV, D1) directly to the template.  Use a separate Worker
  endpoint for any dynamic data needs (e.g. the email subscription form above).
- Changing `custom_page_html` via the API triggers a short propagation delay
  (~30 s) before the new template is live at all PoPs.

---

## Verification

```bash
# Retrieve the current template for a room
curl -sS \
  "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/waiting_rooms/${ROOM_ID}" \
  -H "Authorization: Bearer ${TOKEN}" | jq '.result.custom_page_html | length'
# Should return the character count of your template (> 0 if set)

# Preview the waiting room page (replace with your zone hostname)
# First put the room into force-queue mode via dashboard, then visit:
curl -sI https://example.com/your-protected-path \
  | grep -i "cf-ray\|x-queue-position\|retry-after"
```

---

## Related

- `cloudflare-waiting-room-event-queue-workers.md` — Waiting Room event-based
  queuing and threshold configuration
- `waiting-room-traffic-management-queuing.md` — session duration, total active
  users, and queue-all mechanics
- `workers-queues-patterns.md` — using Workers Queues to handle notifications
  triggered from the email opt-in form
- `cloudflare-for-saas-custom-hostnames.md` — serving waiting rooms on custom
  hostnames for multi-tenant SaaS platforms
- `cloudflare-turnstile-invisible-widget-server-validation.md` — adding
  Turnstile to the waiting room page to prevent bot queue-squatting

---

## Sources

- Waiting Room custom templates:
  https://developers.cloudflare.com/waiting-room/additional-options/customize-waiting-room/
- Waiting Room template variables reference:
  https://developers.cloudflare.com/waiting-room/reference/waiting-room-variables/
- Waiting Room API:
  https://developers.cloudflare.com/api/operations/waiting-room-update-waiting-room
- Waiting Room events (for `eventStartsAt`):
  https://developers.cloudflare.com/waiting-room/additional-options/create-events/
