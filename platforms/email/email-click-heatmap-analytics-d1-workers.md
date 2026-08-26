# Email Click Heatmap Analytics — D1 + Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Standard click tracking tells you *that* a link was clicked and *how many times*, but not *which part of the email* subscribers engage with most. You want a visual click heatmap: given a rendered snapshot of the campaign, overlay click density on each link zone so you can answer "did subscribers read all the way to the third CTA, or did they only engage with the top fold?"

## Context

Email heatmaps are typically an ESP premium feature. Building one in-house requires three pieces: (1) normalised link coordinates stored at template-design time (or derived from a reference render), (2) click events recorded in D1 with the originating link identifier, and (3) a read API that returns per-link click share. A static campaign snapshot in R2 serves as the heatmap canvas; the Worker overlays SVG hotspot annotations at query time.

Unlike web heatmaps, email heatmaps cannot use cursor position — every "heat source" is a discrete link zone, not a continuous pointer trace. The result is a zone-intensity map, not a gradient heatmap in the Hotjar sense, but it communicates the same insight.

---

## 1. D1 schema

```sql
CREATE TABLE campaign_link_zones (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  link_id     TEXT NOT NULL,             -- stable identifier (slug or index)
  url         TEXT NOT NULL,
  label       TEXT,                      -- "CTA 1", "Banner", "Nav Link"
  x_pct       REAL NOT NULL,            -- centre X as % of template width
  y_pct       REAL NOT NULL,            -- centre Y as % of template height
  width_pct   REAL NOT NULL,
  height_pct  REAL NOT NULL,
  UNIQUE(campaign_id, link_id)
);

CREATE TABLE email_link_clicks (
  id          TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  link_id     TEXT NOT NULL,
  recipient_id TEXT,
  clicked_at  TEXT NOT NULL DEFAULT (datetime('now')),
  user_agent  TEXT,
  ip_country  TEXT
);

CREATE INDEX idx_clicks_campaign_link ON email_link_clicks(campaign_id, link_id);
CREATE INDEX idx_clicks_campaign      ON email_link_clicks(campaign_id);
```

## 2. Register link zones at send preparation time

```typescript
interface LinkZone {
  linkId: string;
  url: string;
  label?: string;
  x: number;   // percentage
  y: number;
  width: number;
  height: number;
}

async function registerLinkZones(
  db: D1Database,
  campaignId: string,
  zones: LinkZone[]
): Promise<void> {
  const stmt = db.prepare(`
    INSERT INTO campaign_link_zones
      (id, campaign_id, link_id, url, label, x_pct, y_pct, width_pct, height_pct)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(campaign_id, link_id) DO UPDATE SET
      x_pct = excluded.x_pct, y_pct = excluded.y_pct,
      width_pct = excluded.width_pct, height_pct = excluded.height_pct
  `);

  await db.batch(
    zones.map((z) =>
      stmt.bind(
        crypto.randomUUID(), campaignId, z.linkId, z.url,
        z.label ?? null, z.x, z.y, z.width, z.height
      )
    )
  );
}
```

Coordinates can be extracted from your template system's layout definitions (MJML column/section geometry) or measured manually against a reference screenshot stored in R2.

## 3. Record clicks with geographic context

```typescript
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    // Path: /c/{campaignId}/{linkId}/{recipientToken}
    const [, , campaignId, linkId, recipientToken] = url.pathname.split("/");

    const cf = req.cf as { country?: string };

    await env.DB.prepare(`
      INSERT INTO email_link_clicks
        (id, campaign_id, link_id, recipient_id, user_agent, ip_country)
      VALUES (?, ?, ?, ?, ?, ?)
    `).bind(
      crypto.randomUUID(),
      campaignId,
      linkId,
      recipientToken ?? null,
      req.headers.get("User-Agent") ?? null,
      cf?.country ?? null
    ).run();

    // Look up destination URL and redirect
    const zone = await env.DB.prepare(
      "SELECT url FROM campaign_link_zones WHERE campaign_id = ? AND link_id = ?"
    ).bind(campaignId, linkId).first<{ url: string }>();

    if (!zone) return new Response("Not found", { status: 404 });
    return Response.redirect(zone.url, 302);
  },
};
```

## 4. Compute per-link click intensity

```typescript
interface HeatmapPoint {
  linkId: string;
  label: string | null;
  url: string;
  clicks: number;
  uniqueRecipients: number;
  shareOfTotal: number;      // 0–1
  intensity: number;          // 0–1, log-normalised
  zone: { x: number; y: number; width: number; height: number };
}

async function getCampaignHeatmap(
  db: D1Database,
  campaignId: string
): Promise<HeatmapPoint[]> {
  const rows = await db.prepare(`
    SELECT
      z.link_id,
      z.label,
      z.url,
      z.x_pct        AS x,
      z.y_pct        AS y,
      z.width_pct    AS width,
      z.height_pct   AS height,
      COUNT(c.id)                        AS clicks,
      COUNT(DISTINCT c.recipient_id)     AS unique_recipients
    FROM campaign_link_zones z
    LEFT JOIN email_link_clicks c
      ON c.campaign_id = z.campaign_id AND c.link_id = z.link_id
    WHERE z.campaign_id = ?
    GROUP BY z.link_id
    ORDER BY clicks DESC
  `).bind(campaignId).all<HeatmapRow>();

  const totalClicks = rows.results.reduce((s, r) => s + r.clicks, 0);
  const maxClicks = rows.results[0]?.clicks ?? 1;

  return rows.results.map((r) => ({
    linkId: r.link_id,
    label: r.label,
    url: r.url,
    clicks: r.clicks,
    uniqueRecipients: r.unique_recipients,
    shareOfTotal: totalClicks > 0 ? r.clicks / totalClicks : 0,
    intensity: r.clicks > 0 ? Math.log1p(r.clicks) / Math.log1p(maxClicks) : 0,
    zone: { x: r.x, y: r.y, width: r.width, height: r.height },
  }));
}
```

Log-normalisation (`Math.log1p`) prevents a dominant CTA from washing out all other zones.

## 5. Render SVG overlay for dashboard

```typescript
function renderHeatmapSvg(
  points: HeatmapPoint[],
  templateWidthPx = 600,
  templateHeightPx = 1200
): string {
  const rects = points
    .filter((p) => p.clicks > 0)
    .map((p) => {
      const x = (p.zone.x / 100) * templateWidthPx;
      const y = (p.zone.y / 100) * templateHeightPx;
      const w = (p.zone.width / 100) * templateWidthPx;
      const h = (p.zone.height / 100) * templateHeightPx;
      // Interpolate hue: 240 (cool blue, low) → 0 (red, high)
      const hue = Math.round(240 - p.intensity * 240);
      const opacity = 0.15 + p.intensity * 0.65;
      return `
        <rect x="${x}" y="${y}" width="${w}" height="${h}"
          fill="hsl(${hue},90%,55%)" fill-opacity="${opacity.toFixed(2)}" rx="3"/>
        <text x="${x + w / 2}" y="${y + h / 2 + 4}" text-anchor="middle"
          font-size="11" fill="white" font-weight="600">${p.clicks}</text>`;
    })
    .join("");

  return `<svg xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 ${templateWidthPx} ${templateHeightPx}"
    width="${templateWidthPx}" height="${templateHeightPx}">${rects}</svg>`;
}
```

Layer this SVG over the R2-hosted campaign screenshot in your dashboard with `position: absolute; top: 0; left: 0`.

---

## Anti-patterns

- **Using pixel coordinates instead of percentages** — template renders vary by device; percentage-based zones adapt to any render width.
- **Counting bot clicks in heatmap data** — filter out known bot user agents and clicks arriving within 30 seconds of delivery (common for URL prefetch bots before recording).
- **Building a continuous gradient heatmap** — email is a discrete-link medium; misrepresenting it as a continuous surface misleads designers.
- **Storing one click row per page load** — use an idempotency window: if the same recipient clicks the same link within 5 seconds, deduplicate (multiple HTTP retries from MUAs).

## Gotchas

- Zone coordinates must be registered per campaign variant — an A/B test may have different CTA positions.
- `req.cf.country` is only available on Workers routes with a Cloudflare-proxied domain; it is absent in local dev (`wrangler dev`). Guard with a null check.
- D1 `LEFT JOIN` with `COUNT(c.id)` returns 0 for links with no clicks — this is intentional; do not filter `clicks = 0` rows out before passing to `renderHeatmapSvg`.
- High-cardinality link-id values (one per recipient) break the `GROUP BY` aggregation. Use a canonical link identifier that is the same for all recipients (link slot position), not a per-recipient token.

## Verification

1. Register three zones for a test campaign; simulate clicks at a 3:1:0 ratio; confirm `intensity` values are approximately 1.0, 0.63, 0.0.
2. Render the SVG overlay and confirm the red zone corresponds to the highest-click link slot.
3. Verify bot-click filtering by sending a HEAD request to a click URL and confirming it does not increment the click count (HEAD should not trigger a DB insert).

## Related

- `email-click-tracking.md`
- `email-click-tracking-privacy-preserving-workers.md`
- `email-open-click-analytics-engine.md`
- `email-link-health-monitoring-workers-kv.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/workers/runtime-apis/request/#incomingrequestcfproperties
- https://mjml.io/documentation/#standard-body-components
