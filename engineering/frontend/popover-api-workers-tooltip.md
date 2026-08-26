# Popover API Tooltips Backed by Workers Data

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need rich, accessible tooltips that display live data (user profiles, product summaries,
link previews) fetched from a Cloudflare Worker — without a heavyweight UI library.

## Context
The HTML Popover API (`popover` attribute + `popovertarget`) is now Baseline 2024 and provides
focus-managed, dismiss-on-Escape overlays with no JavaScript required for simple cases.
Pairing it with a Cloudflare Worker endpoint allows tooltip content to be fetched on-demand and
cached at the edge, keeping the initial HTML payload small. The Worker serves JSON; the browser
renders it into the popover using the Sanitizer API (or `textContent` for plain strings) to
prevent XSS from dynamic content.

---

## Worker: Tooltip Data Endpoint

```typescript
// workers/tooltip-api/src/index.ts
export interface Env {
  DB: D1Database;
}

interface UserSummary {
  id: string;
  displayName: string;
  avatarUrl: string;
  role: string;
  joinedDate: string;
  postCount: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    // Route: /tooltip/user/:id
    const userMatch = url.pathname.match(/^\/tooltip\/user\/([a-zA-Z0-9_-]{1,64})$/);
    if (userMatch) {
      return handleUserTooltip(userMatch[1], env);
    }

    // Route: /tooltip/post/:slug
    const postMatch = url.pathname.match(/^\/tooltip\/post\/([a-zA-Z0-9_-]{1,128})$/);
    if (postMatch) {
      return handlePostTooltip(postMatch[1], env);
    }

    return new Response("Not Found", { status: 404 });
  },
} satisfies ExportedHandler<Env>;

async function handleUserTooltip(userId: string, env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    `SELECT id, display_name, avatar_url, role, joined_date, post_count
     FROM users WHERE id = ? LIMIT 1`
  ).bind(userId).first<UserSummary>();

  if (!row) return new Response("Not Found", { status: 404 });

  const payload: UserSummary = {
    id: row.id,
    displayName: row.display_name,
    avatarUrl: row.avatar_url,
    role: row.role,
    joinedDate: row.joined_date,
    postCount: row.post_count,
  };

  return Response.json(payload, {
    headers: {
      "Cache-Control": "public, max-age=300, stale-while-revalidate=60",
      "Access-Control-Allow-Origin": "https://mysite.pages.dev",
    },
  });
}

async function handlePostTooltip(slug: string, env: Env): Promise<Response> {
  const row = await env.DB.prepare(
    `SELECT title, excerpt, published_date, author_name FROM posts WHERE slug = ? LIMIT 1`
  ).bind(slug).first();

  if (!row) return new Response("Not Found", { status: 404 });

  return Response.json(row, {
    headers: {
      "Cache-Control": "public, max-age=600",
      "Access-Control-Allow-Origin": "https://mysite.pages.dev",
    },
  });
}
```

---

## HTML Markup Pattern

```html
<!--
  Trigger button uses popovertarget to link to the popover element.
  The popover itself starts empty; JS populates it before show.
-->
<span
  class="user-mention"
  data-tooltip-type="user"
  data-tooltip-id="usr_abc123"
  aria-describedby="tooltip-panel"
>
  @alice
  <button
    type="button"
    class="tooltip-trigger"
    popovertarget="tooltip-panel"
    popovertargetaction="toggle"
    aria-label="Show profile for alice"
  >ℹ</button>
</span>

<!-- Shared popover panel — one per page, repositioned per trigger -->
<div
  id="tooltip-panel"
  popover="auto"
  role="tooltip"
  class="tooltip-popover"
>
  <div id="tooltip-content" class="tooltip-body">
    <!-- Populated dynamically -->
  </div>
</div>
```

---

## Client-Side Tooltip Controller

```typescript
// src/lib/workersTooltip.ts

const API_BASE = "https://tooltip-api.myworker.workers.dev";
const CACHE = new Map<string, unknown>();

interface UserSummary {
  id: string;
  displayName: string;
  avatarUrl: string;
  role: string;
  joinedDate: string;
  postCount: number;
}

async function fetchTooltipData(type: string, id: string): Promise<unknown> {
  const key = `${type}:${id}`;
  if (CACHE.has(key)) return CACHE.get(key);

  const res = await fetch(`${API_BASE}/tooltip/${type}/${encodeURIComponent(id)}`);
  if (!res.ok) throw new Error(`Tooltip fetch failed: ${res.status}`);

  const data = await res.json();
  CACHE.set(key, data);
  return data;
}

function renderUserTooltip(data: UserSummary): string {
  // Use textContent assignment (below) for each field — never innerHTML with raw data.
  return "user"; // sentinel; actual DOM manipulation done in mountTooltip
}

function mountTooltip(
  contentEl: HTMLElement,
  type: string,
  data: unknown
): void {
  contentEl.innerHTML = ""; // clear previous

  if (type === "user") {
    const u = data as UserSummary;

    const avatar = document.createElement("img");
    avatar.src = u.avatarUrl;
    avatar.alt = "";
    avatar.width = 48;
    avatar.height = 48;
    avatar.className = "tooltip-avatar";

    const name = document.createElement("strong");
    name.textContent = u.displayName;

    const role = document.createElement("span");
    role.className = "tooltip-role";
    role.textContent = u.role;

    const meta = document.createElement("p");
    meta.className = "tooltip-meta";
    meta.textContent = `${u.postCount} posts · Joined ${u.joinedDate}`;

    const header = document.createElement("div");
    header.className = "tooltip-header";
    header.append(avatar, name, role);

    contentEl.append(header, meta);
  }
}

export function initWorkerTooltips(): void {
  const panel = document.getElementById("tooltip-panel") as HTMLElement & {
    showPopover(): void;
    hidePopover(): void;
  } | null;
  const content = document.getElementById("tooltip-content");
  if (!panel || !content) return;

  // Intercept the popover toggle to load data first
  document.addEventListener("click", async (e) => {
    const btn = (e.target as Element).closest<HTMLButtonElement>("[popovertarget='tooltip-panel']");
    if (!btn) return;

    // Identify the trigger's parent mention element
    const mention = btn.closest<HTMLElement>("[data-tooltip-type]");
    if (!mention) return;

    const type = mention.dataset.tooltipType!;
    const id = mention.dataset.tooltipId!;

    // Position popover near trigger using anchor-positioning fallback
    const rect = btn.getBoundingClientRect();
    panel.style.setProperty("--tooltip-top", `${rect.bottom + window.scrollY + 8}px`);
    panel.style.setProperty("--tooltip-left", `${rect.left + window.scrollX}px`);

    content.textContent = "Loading…";

    try {
      const data = await fetchTooltipData(type, id);
      mountTooltip(content, type, data);
    } catch {
      content.textContent = "Failed to load.";
    }
  });
}
```

```typescript
// src/main.ts
import { initWorkerTooltips } from "./lib/workersTooltip";
document.addEventListener("DOMContentLoaded", initWorkerTooltips);
```

---

## CSS

```css
/* Baseline reset for popover */
[popover] {
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
}

.tooltip-popover {
  position: absolute;
  top: var(--tooltip-top, 0);
  left: var(--tooltip-left, 0);
  width: 260px;
  background: var(--surface-raised, #1e293b);
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  padding: 14px;
  color: var(--text-primary, #f1f5f9);
  font-size: 0.875rem;

  /* Entry animation (supported where ::backdrop is) */
  &:popover-open {
    animation: tooltip-in 0.15s ease;
  }
}

@keyframes tooltip-in {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.tooltip-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.tooltip-avatar {
  border-radius: 50%;
  object-fit: cover;
}

.tooltip-role {
  display: block;
  font-size: 0.75rem;
  color: var(--text-muted, #94a3b8);
}

.tooltip-meta {
  font-size: 0.75rem;
  color: var(--text-muted, #94a3b8);
  margin: 0;
}
```

---

## Anti-patterns
- Using `innerHTML` with raw Worker response data — always sanitize or use `textContent`/DOM APIs
- Creating a separate popover element per trigger — one shared panel is sufficient and avoids DOM bloat
- Not caching fetch results in a `Map` — repeated hovers re-fetch the same data
- Opening the popover before the fetch resolves — leads to empty popover flash; populate first, then show
- Using `popover="hint"` for rich content — `hint` is single-line only; use `popover="auto"` for cards

## Gotchas
- `popovertarget` triggers the built-in show/hide toggle before your `click` listener fires; intercept with `beforetoggle` event if you need to cancel the default
- `popover="auto"` dismisses on outside click and Escape automatically — no manual listener needed
- Absolute positioning via CSS variables works but CSS Anchor Positioning (`anchor()`) is the spec-correct approach once widely supported
- The popover element must be a direct child of `<body>` (or a top-layer ancestor) to avoid stacking-context clipping from parent elements
- D1 queries in tooltip Workers should use prepared statements to avoid SQL injection from user-supplied IDs

## Verification
```bash
# Confirm D1 query returns expected shape
wrangler d1 execute MY_DB --command \
  "SELECT id, display_name, avatar_url, role, joined_date, post_count FROM users WHERE id='usr_abc123'"

# Check Worker response headers and body
curl -s https://tooltip-api.myworker.workers.dev/tooltip/user/usr_abc123 | jq .

# Verify cache header
curl -I https://tooltip-api.myworker.workers.dev/tooltip/user/usr_abc123 | grep Cache-Control
# Expected: Cache-Control: public, max-age=300, stale-while-revalidate=60

# Accessibility: ensure popover has role=tooltip and is linked via aria-describedby
npx axe https://mysite.pages.dev --include="#tooltip-panel"
```

## Related
- `native-popover-dialog-anchor.md`
- `html-invoker-commands-dialog-and-popover-controls.md`
- `css-anchor-positioning-overflow-fallbacks.md`
- `hono-cloudflare-workers-frontend-api.md`
- `trusted-types-xss-prevention-workers.md`

## Sources
- https://developer.mozilla.org/en-US/docs/Web/API/Popover_API
- https://html.spec.whatwg.org/multipage/popover.html
- https://developers.cloudflare.com/d1/
- https://web.dev/popover-api/
- https://developer.chrome.com/blog/anchor-positioning-api/
