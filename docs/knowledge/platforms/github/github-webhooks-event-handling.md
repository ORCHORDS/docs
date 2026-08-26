# github-webhooks-event-handling

**Issue:** Receiving and validating GitHub webhook payloads in a custom server
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You need to react to GitHub events (push, PR, issue) in your own service rather than inside Actions.

## Pattern / Solution
Node.js validation with `@octokit/webhooks`:
```js
import { Webhooks } from "@octokit/webhooks";
const webhooks = new Webhooks({ secret: process.env.WEBHOOK_SECRET });

app.post("/webhook", async (req, res) => {
  const signature = req.headers["x-hub-signature-256"];
  if (!(await webhooks.verify(req.rawBody, signature))) {
    return res.status(401).send("Unauthorized");
  }
  res.status(200).send("ok");
});
```
Register the webhook in repo Settings → Webhooks → Add webhook. Select individual events to minimise payload volume.

## Gotchas
- Always verify the `X-Hub-Signature-256` HMAC header before processing.
- GitHub retries failed deliveries with exponential backoff up to 3 days.
- Respond with HTTP 200 within 10 seconds or GitHub marks the delivery as failed.
- Use `rawBody` (not parsed JSON) for HMAC verification — parsing mutates byte ordering.
- `X-Hub-Signature` (SHA-1) is deprecated; use `X-Hub-Signature-256` (SHA-256).

## Related
- `github-apps-installation-tokens.md`
- `github-api-rate-limiting.md`
